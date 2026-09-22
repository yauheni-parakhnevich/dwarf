import Foundation

public enum Mode: String, Equatable, Codable, Sendable {
    case disarmed
    case dryRun = "dry-run"
    case live
    case calibration
}

public struct FireLimits: Equatable, Sendable {
    /// Shortest gap between two shots at the same animal, by track id. Kept keyed by id
    /// rather than place: it only ever needs to hold across two consecutive shots at one
    /// still-live track, and a churned id can only make it stricter (a fresh id has no
    /// recorded last shot, so it never shortens the gap), never looser.
    public var minShotInterval: TimeInterval = 10
    /// A deterrent, not a punishment: shots at the same physical animal, judged by how
    /// close in place and time they landed (see `animalRadius`, `animalWindow`) rather than
    /// by track id. A tracker id churns on any occlusion or detector gap longer than the
    /// tracker's drop timeout, or when two cats cross — none of which end an animal's visit,
    /// so a cap keyed by id alone resets exactly when it matters least.
    public var maxShotsPerAnimal: Int = 3
    /// How close two shots' ground points must be, in normalised frame units, to count as
    /// the same animal for `maxShotsPerAnimal`.
    public var animalRadius: Double = 0.15
    /// How long a shot keeps counting toward `maxShotsPerAnimal` at its location before it
    /// ages out. Generous on purpose: a cat that returns to a different corner ten minutes
    /// later is a new visit and should get a fresh budget, not inherit the last one's.
    public var animalWindow: TimeInterval = 600
    /// Shortest gap between any two shots, whatever they are aimed at. The gnome has one
    /// nozzle and one pump, and the firmware enforces its own 5 s cooldown: a `shoot` that
    /// arrives inside it is refused, so asking anyway would spend an animal's budget on
    /// water it never received. 6 s covers the firmware's 5 s (which starts when the valve
    /// closes, not when the command arrives), plus the servo move, the 150 ms settle, the
    /// burst itself and the BLE round trip. Distinct from `minShotInterval`, which is
    /// about how often one animal should be sprayed rather than what the hardware can do.
    public var minDeviceInterval: TimeInterval = 6
    /// A ceiling on the whole system, whatever the tracker believes it is seeing.
    public var maxShotsPerHour: Int = 20
    /// Length of one burst. The spec's welfare range is 200...400 ms, and `FirePolicy`
    /// clamps into it: see `FirePolicy.limits`.
    public var burstMs: UInt16 = 300
    /// Active window in local time, as hours.
    public var activeStartHour: Int = 7
    public var activeEndHour: Int = 20
    /// Mean luma below which the scene is too dark to judge.
    public var darkLuma: Double = 40
    /// Closer than this the jet is a hard stream; never fire.
    public var minRangeM: Double = 2
    /// Aim updates per second while following a cat.
    public var aimInterval: TimeInterval = 0.2
    /// Idle time before the head returns to centre.
    public var parkAfter: TimeInterval = 10
    /// How long a track may be continuously, structurally unfireable — standing in a
    /// no-fire zone, too close, or carrying a flagged aim solution — before the head stops
    /// chasing it and parks. Behavioural reasons (not yet confirmed, not yet still, tangled
    /// with another track) and rate limits (cooldown, the per-animal or hourly cap) do not
    /// count toward this: see `FirePolicy.isStructurallyUnfireable`.
    public var aimBackoffAfter: TimeInterval = 30

    public init() {}
}

/// Everything the policy needs for one decision. Passed in rather than read, so the rules
/// are testable with a fake clock.
public struct PolicyInput: Sendable {
    public var mode: Mode
    public var tracks: [Track]
    /// Aim solutions by track id. A track without one cannot be fired at.
    public var solutions: [Int: AimSolution]
    public var masks: MaskSet
    /// The last status from the ESP32, or nil if none has arrived.
    public var status: DeviceStatus?
    public var meanLuma: Double
    /// Wall clock, used only for the active window.
    public var now: Date
    /// Monotonic seconds, used for every interval and cooldown. Trusted as given — this
    /// policy never reads a clock itself. A value that ever decreases (a monotonic counter
    /// reset across a reboot, say) makes every interval look freshly reset rather than
    /// elapsed, so cooldowns and caps would read as still active for longer than intended.
    /// That fails safe (stuck closed, never stuck open), which is why it is written down
    /// here rather than guarded against.
    public var uptime: TimeInterval

    public init(mode: Mode, tracks: [Track], solutions: [Int: AimSolution], masks: MaskSet,
                status: DeviceStatus?, meanLuma: Double, now: Date, uptime: TimeInterval) {
        self.mode = mode
        self.tracks = tracks
        self.solutions = solutions
        self.masks = masks
        self.status = status
        self.meanLuma = meanLuma
        self.now = now
        self.uptime = uptime
    }
}

/// Why the policy did not fire at the animal it was considering.
public enum FireRefusal: String, Equatable, Sendable, CaseIterable {
    /// Disarmed, or in calibration: the system is not operating at all.
    case notOperating
    case notConfirmed
    case notStill
    /// Too close to another track to trust which history belongs to which animal.
    case ambiguous
    /// The aim solution itself cannot be trusted — outside the servo limits, outside the
    /// calibrated area, or no height offset for this range.
    case aimFlagged
    /// Inside the minimum range, where the jet is a hard stream rather than a spray.
    case tooClose
    case noFireZone
    /// No status, or one too old to believe. The link is down or silent.
    case noFreshStatus
    /// The gnome answered, and said it cannot fire: disarmed, tank empty, or a fault.
    case deviceNotReady
    case animalCapReached
    case hourlyCapReached
    case animalCoolingDown
    /// One nozzle, and the firmware would refuse a shot this soon after the last.
    case nozzleCoolingDown
    /// No aim could be computed at all, which in practice means an uncalibrated gnome.
    case noAimSolution
}

public enum FireDecision: Equatable, Sendable {
    case none
    case aim(pan: Double, tilt: Double)
    case shoot(pan: Double, tilt: Double, ms: UInt16)
    /// Dry-run: everything passed, but no water. Logged for review.
    case wouldShoot(pan: Double, tilt: Double, ms: UInt16)
    case park
}

/// Decides what the gnome does this cycle. The only place in the project allowed to ask for
/// water.
public final class FirePolicy {
    /// Clamped into the spec's welfare envelope whenever it is set: the burst length into
    /// 200...400 ms, and the minimum range to no less than 2 m. Those two numbers are what
    /// decide whether this is water landing on a cat or a hard stream aimed at one, and
    /// both are plain settings a screen that does not exist yet could bind straight to.
    /// Everything else is taken exactly as given.
    public var limits: FireLimits {
        didSet { limits = FirePolicy.withinWelfareEnvelope(limits) }
    }

    private var lastShotByTrack: [Int: TimeInterval] = [:]
    /// Every shot's ground point and uptime, live or dry-run, pruned to `animalWindow` on
    /// read. This is what `maxShotsPerAnimal` is judged against instead of a track id.
    private var shotHistory: [(point: Point, uptime: TimeInterval)] = []
    private var recentShots: [TimeInterval] = []
    /// When each track id most recently became structurally unfireable, if it is currently
    /// in an unbroken streak of that. Cleared the moment it fires or stops being
    /// structurally unfireable. See `isStructurallyUnfireable`.
    private var refusedSince: [Int: TimeInterval] = [:]
    /// Why the best candidate was not fired at this cycle, or nil when it was. Reset to
    /// nil when there is nothing to consider at all.
    public private(set) var lastRefusal: FireRefusal?
    private var lastAim: TimeInterval?
    private var lastActivity: TimeInterval?
    private var parked = true

    public init(limits: FireLimits = FireLimits()) {
        self.limits = FirePolicy.withinWelfareEnvelope(limits)
    }

    private static func withinWelfareEnvelope(_ limits: FireLimits) -> FireLimits {
        var clamped = limits
        clamped.burstMs = min(max(limits.burstMs, 200), 400)
        // A non-finite minimum range would make every range comparison false, which reads
        // as "never too close" — the wrong way for this particular guard to fail.
        clamped.minRangeM = limits.minRangeM.isFinite ? max(limits.minRangeM, 2) : 2
        return clamped
    }

    public func decide(_ input: PolicyInput) -> FireDecision {
        // The system itself has stopped operating this cycle, not merely run out of
        // things to look at: return the head to centre immediately rather than leaving it
        // aimed wherever it last was until the window reopens.
        guard input.mode != .disarmed, input.mode != .calibration else { return parkForInactivity() }
        guard isDaylight(input) else { return parkForInactivity() }

        let candidates = input.tracks
            .filter { !input.masks.isIgnored($0.groundPoint) }
            // Ties broken by id so the choice does not depend on sort stability or on the
            // order the tracker happens to hand its states over in.
            .sorted { $0.confidence == $1.confidence ? $0.id < $1.id : $0.confidence > $1.confidence }

        guard !candidates.isEmpty else {
            lastRefusal = nil
            return parkIfIdle(input.uptime)
        }

        // One nozzle means one animal at a time, but it must not mean the same animal
        // forever. Ranking by confidence alone let a cat that had already used up its
        // budget keep the head pointed at itself for as long as it stayed in frame, while
        // a second cat sat untreated a metre away: every cycle picked the top-ranked track,
        // found it merely rate-limited rather than structurally unfireable, and aimed at it
        // again. So a candidate that can actually be fired at now wins; if none can, the
        // best-ranked one still gets the head pre-positioned as before.
        let best = candidates.first { candidate in
            guard let solution = input.solutions[candidate.id] else { return false }
            return canFire(candidate, solution, input)
        } ?? candidates[0]

        // Recorded for whoever is watching, about the animal actually being considered.
        if let solution = input.solutions[best.id] {
            lastRefusal = refusal(best, solution, input)
        } else {
            lastRefusal = .noAimSolution
        }

        guard let solution = input.solutions[best.id] else {
            lastActivity = input.uptime
            parked = false
            return aimIfDue(pan: nil, tilt: nil, at: input.uptime)
        }

        if canFire(best, solution, input) {
            refusedSince[best.id] = nil
            lastActivity = input.uptime
            parked = false
            // Recorded for dry-run exactly as for live: a dry run whose logs do not predict
            // what live operation will do is worthless, which is the entire reason dry-run
            // exists. Both modes share one cooldown/cap history on purpose.
            record(shot: best.id, at: best.groundPoint, uptime: input.uptime)
            lastAim = input.uptime
            return input.mode == .live
                ? .shoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
                : .wouldShoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
        }

        if isStructurallyUnfireable(best, solution, input) {
            let since = refusedSince[best.id] ?? input.uptime
            refusedSince[best.id] = since
            if input.uptime - since >= limits.aimBackoffAfter {
                // Stop grinding the servo at an animal that cannot be fired at from where
                // it is standing and has not moved in half a minute. Deliberately leaves
                // `lastActivity` alone: if this track later vanishes with no other activity,
                // parkIfIdle should not additionally reset the parked clock we just set.
                // Guarded so a track refused for the whole afternoon parks once, not every
                // cycle, exactly like the other two park sites.
                guard !parked else { return .none }
                return performPark()
            }
        } else {
            refusedSince[best.id] = nil
        }

        lastActivity = input.uptime
        parked = false
        return aimIfDue(pan: solution.pan, tilt: solution.tilt, at: input.uptime)
    }

    private func canFire(_ track: Track, _ solution: AimSolution, _ input: PolicyInput) -> Bool {
        refusal(track, solution, input) == nil
    }

    /// Every condition, in one place, and why it said no. Each line is a rule from the spec.
    ///
    /// Returning the reason rather than a bare false is what makes a gnome diagnosable. It
    /// spends most of its life not firing, and "not confirmed yet" and "standing in a
    /// no-fire zone" and "the tank is empty" all used to collapse into the same silent
    /// verdict. The owner's question is never "did it fire" — they can see that — it is
    /// always "why didn't it".
    private func refusal(_ track: Track, _ solution: AimSolution,
                         _ input: PolicyInput) -> FireRefusal? {
        guard input.mode == .live || input.mode == .dryRun else { return .notOperating }
        guard track.isConfirmed else { return .notConfirmed }
        guard track.isStill else { return .notStill }
        // Nearest-neighbour association cannot tell two crossing animals apart, so the
        // tracker flags the overlap rather than guessing. Water while two cats are tangled
        // is exactly when the history behind "confirmed and still" is least trustworthy.
        guard !track.isAmbiguous else { return .ambiguous }
        guard !solution.isFlagged else { return .aimFlagged }
        guard solution.rangeM >= limits.minRangeM else { return .tooClose }
        guard !input.masks.isNoFire(track.groundPoint) else { return .noFireZone }
        guard let status = input.status else { return .noFreshStatus }
        guard status.canFire else { return .deviceNotReady }
        guard shotsNear(track.groundPoint, endingAt: input.uptime) < limits.maxShotsPerAnimal else {
            return .animalCapReached
        }
        guard shotsInLastHour(endingAt: input.uptime) < limits.maxShotsPerHour else {
            return .hourlyCapReached
        }
        if let last = lastShotByTrack[track.id],
           input.uptime - last < limits.minShotInterval { return .animalCoolingDown }
        // The hardware itself, not the animal: one nozzle, and a firmware cooldown that
        // would refuse this shot anyway. See `FireLimits.minDeviceInterval`.
        if let last = recentShots.last,
           input.uptime - last < limits.minDeviceInterval { return .nozzleCoolingDown }
        return nil
    }

    /// Refusal reasons that are about the aim itself — where the animal is standing, or
    /// whether the computed solution can be trusted — as opposed to the animal's momentary
    /// behaviour (not yet confirmed, not yet still, tangled with another track) or a rate
    /// limit (cooldown, the per-animal or hourly cap). Behavioural reasons can clear within
    /// a second or two — the next look confirms the track, the animal settles — so the head
    /// stays pre-positioned and a shot can follow immediately, and the rate limits resolve
    /// on their own as time passes regardless of where the animal is standing. Note that
    /// aiming has no effect on whether a track is seen at all: the camera is fixed in the
    /// gnome's belly and does not move with the head. A cat standing in a no-fire zone, or
    /// beyond the calibrated area, can do that for the rest of the afternoon: aiming at it
    /// is a pure cost with no chance of ever becoming a shot until it moves. See
    /// `FireLimits.aimBackoffAfter`.
    private func isStructurallyUnfireable(_ track: Track, _ solution: AimSolution, _ input: PolicyInput) -> Bool {
        solution.isFlagged || solution.rangeM < limits.minRangeM || input.masks.isNoFire(track.groundPoint)
    }

    private func isDaylight(_ input: PolicyInput) -> Bool {
        guard input.meanLuma >= limits.darkLuma else { return false }
        let hour = Calendar.current.component(.hour, from: input.now)
        return hour >= limits.activeStartHour && hour < limits.activeEndHour
    }

    private func aimIfDue(pan: Double?, tilt: Double?, at uptime: TimeInterval) -> FireDecision {
        guard let pan, let tilt else { return .none }
        if let last = lastAim, uptime - last < limits.aimInterval { return .none }
        lastAim = uptime
        return .aim(pan: pan, tilt: tilt)
    }

    private func parkIfIdle(_ uptime: TimeInterval) -> FireDecision {
        guard !parked else { return .none }
        guard let last = lastActivity, uptime - last >= limits.parkAfter else { return .none }
        return performPark()
    }

    /// The system stopped operating this cycle (disarmed, calibrating, outside the active
    /// window, or too dark to judge) rather than merely having nothing to look at right
    /// now: park immediately, once, instead of waiting out `parkAfter` or leaving the head
    /// aimed at whatever it was tracking until the window reopens.
    private func parkForInactivity() -> FireDecision {
        guard !parked else { return .none }
        return performPark()
    }

    private func performPark() -> FireDecision {
        parked = true
        lastAim = nil
        return .park
    }

    private func record(shot id: Int, at point: Point, uptime: TimeInterval) {
        lastShotByTrack[id] = uptime
        recentShots.append(uptime)
        shotHistory.append((point: point, uptime: uptime))
    }

    /// How many shots are still counted against the hourly ceiling, for a status display.
    public func shotsInLastHour(asOf uptime: TimeInterval) -> Int {
        shotsInLastHour(endingAt: uptime)
    }

    private func shotsInLastHour(endingAt uptime: TimeInterval) -> Int {
        recentShots.removeAll { uptime - $0 > 3600 }
        return recentShots.count
    }

    /// Shots within `animalRadius` of `point` and still inside `animalWindow`, regardless
    /// of which track id they were recorded under. This is the budget `maxShotsPerAnimal`
    /// is judged against, precisely so it survives the track id changing underneath one
    /// physical animal.
    private func shotsNear(_ point: Point, endingAt uptime: TimeInterval) -> Int {
        shotHistory.removeAll { uptime - $0.uptime > limits.animalWindow }
        return shotHistory.filter { $0.point.distance(to: point) <= limits.animalRadius }.count
    }
}
