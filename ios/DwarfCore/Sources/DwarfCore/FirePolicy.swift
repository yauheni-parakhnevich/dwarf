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
    /// A ceiling on the whole system, whatever the tracker believes it is seeing.
    public var maxShotsPerHour: Int = 20
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
    public var limits: FireLimits

    private var lastShotByTrack: [Int: TimeInterval] = [:]
    /// Every shot's ground point and uptime, live or dry-run, pruned to `animalWindow` on
    /// read. This is what `maxShotsPerAnimal` is judged against instead of a track id.
    private var shotHistory: [(point: Point, uptime: TimeInterval)] = []
    private var recentShots: [TimeInterval] = []
    /// When each track id most recently became structurally unfireable, if it is currently
    /// in an unbroken streak of that. Cleared the moment it fires or stops being
    /// structurally unfireable. See `isStructurallyUnfireable`.
    private var refusedSince: [Int: TimeInterval] = [:]
    private var lastAim: TimeInterval?
    private var lastActivity: TimeInterval?
    private var parked = true

    public init(limits: FireLimits = FireLimits()) {
        self.limits = limits
    }

    public func decide(_ input: PolicyInput) -> FireDecision {
        // The system itself has stopped operating this cycle, not merely run out of
        // things to look at: return the head to centre immediately rather than leaving it
        // aimed wherever it last was until the window reopens.
        guard input.mode != .disarmed, input.mode != .calibration else { return parkForInactivity() }
        guard isDaylight(input) else { return parkForInactivity() }

        let candidates = input.tracks
            .filter { !input.masks.isIgnored($0.groundPoint) }
            .sorted { $0.confidence > $1.confidence }

        guard let best = candidates.first else {
            return parkIfIdle(input.uptime)
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

    /// Every condition, in one place. Each line is a rule from the spec.
    private func canFire(_ track: Track, _ solution: AimSolution, _ input: PolicyInput) -> Bool {
        guard input.mode == .live || input.mode == .dryRun else { return false }
        guard track.isConfirmed, track.isStill else { return false }
        // Nearest-neighbour association cannot tell two crossing animals apart, so the
        // tracker flags the overlap rather than guessing. Water while two cats are tangled
        // is exactly when the history behind "confirmed and still" is least trustworthy.
        guard !track.isAmbiguous else { return false }
        guard !solution.isFlagged else { return false }
        guard solution.rangeM >= limits.minRangeM else { return false }
        guard !input.masks.isNoFire(track.groundPoint) else { return false }
        guard let status = input.status, status.canFire else { return false }
        guard shotsNear(track.groundPoint, endingAt: input.uptime) < limits.maxShotsPerAnimal else { return false }
        guard shotsInLastHour(endingAt: input.uptime) < limits.maxShotsPerHour else { return false }
        if let last = lastShotByTrack[track.id],
           input.uptime - last < limits.minShotInterval { return false }
        return true
    }

    /// Refusal reasons that are about the aim itself — where the animal is standing, or
    /// whether the computed solution can be trusted — as opposed to the animal's momentary
    /// behaviour (not yet confirmed, not yet still, tangled with another track) or a rate
    /// limit (cooldown, the per-animal or hourly cap). The behavioural reasons are expected
    /// to resolve only if the head keeps looking — a track cannot become confirmed if
    /// nothing keeps sampling it — and the rate limits resolve on their own as time passes
    /// regardless of where the animal is standing. A cat standing in a no-fire zone, or
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
