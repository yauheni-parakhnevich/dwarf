import Foundation

public enum Mode: String, Equatable, Codable, Sendable {
    case disarmed
    case dryRun = "dry-run"
    case live
    case calibration
}

public struct FireLimits: Equatable, Sendable {
    /// Shortest gap between two shots at the same animal.
    public var minShotInterval: TimeInterval = 10
    /// A deterrent, not a punishment.
    public var maxShotsPerTrack: Int = 3
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
    /// Monotonic seconds, used for every interval and cooldown.
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

    private var shotsByTrack: [Int: Int] = [:]
    private var lastShotByTrack: [Int: TimeInterval] = [:]
    private var recentShots: [TimeInterval] = []
    private var lastAim: TimeInterval?
    private var lastActivity: TimeInterval?
    private var parked = true

    public init(limits: FireLimits = FireLimits()) {
        self.limits = limits
    }

    public func decide(_ input: PolicyInput) -> FireDecision {
        guard input.mode != .disarmed, input.mode != .calibration else { return .none }
        guard isDaylight(input) else { return .none }

        let candidates = input.tracks
            .filter { !input.masks.isIgnored($0.groundPoint) }
            .sorted { $0.confidence > $1.confidence }

        guard let best = candidates.first else {
            return parkIfIdle(input.uptime)
        }

        lastActivity = input.uptime
        parked = false

        guard let solution = input.solutions[best.id] else {
            return aimIfDue(pan: nil, tilt: nil, at: input.uptime)
        }

        if canFire(best, solution, input) {
            record(shot: best.id, at: input.uptime)
            lastAim = input.uptime
            return input.mode == .live
                ? .shoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
                : .wouldShoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
        }

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
        guard shotsByTrack[track.id, default: 0] < limits.maxShotsPerTrack else { return false }
        guard shotsInLastHour(endingAt: input.uptime) < limits.maxShotsPerHour else { return false }
        if let last = lastShotByTrack[track.id],
           input.uptime - last < limits.minShotInterval { return false }
        return true
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
        parked = true
        lastAim = nil
        return .park
    }

    private func record(shot id: Int, at uptime: TimeInterval) {
        shotsByTrack[id, default: 0] += 1
        lastShotByTrack[id] = uptime
        recentShots.append(uptime)
    }

    private func shotsInLastHour(endingAt uptime: TimeInterval) -> Int {
        recentShots.removeAll { uptime - $0 > 3600 }
        return recentShots.count
    }
}
