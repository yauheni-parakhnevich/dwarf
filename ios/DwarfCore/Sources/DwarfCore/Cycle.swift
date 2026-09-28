import Foundation

/// What one cycle produced: what to do now, what the detector should look at next, and
/// enough state for the web UI to draw.
public struct CycleOutput: Sendable {
    public let decision: FireDecision
    public let cropRequests: [CropRequest]
    public let tracks: [Track]
    public let solutions: [Int: AimSolution]
    public let blobs: [Blob]
    public let meanLuma: Double
    /// Why the best candidate was not fired at, or nil when it was, or when there was
    /// nothing to consider. See `FireRefusal`.
    public let refusal: FireRefusal?
    /// Shots still counted against the hourly ceiling.
    public let shotsThisHour: Int
}

/// Runs a frame through the whole pipeline.
///
/// Owns the stateful parts. Detection happens outside and arrives late — the crops asked for
/// this cycle come back a cycle or two later — and this class does not pretend otherwise.
public final class Cycle {
    public var mode: Mode = .dryRun
    public var masks: MaskSet = .empty

    private let motion: MotionDetector
    private let scheduler: Scheduler
    private let tracker: Tracker
    private let policy: FirePolicy
    private var aimer: Aimer?
    /// Capture time of the newest detector answer applied so far.
    private var lastAnswerAt: TimeInterval?

    /// Never fails. The *aimer* is what may be absent: an uncalibrated gnome must still
    /// boot, track and show a live view, otherwise it could never be calibrated in the
    /// first place. Without an aimer nothing can be fired, because FirePolicy requires a
    /// solution for the track it is considering.
    public init(calibration: Calibration,
                 limits: AimLimits = AimLimits(),
                 fireLimits: FireLimits = FireLimits(),
                 motionConfig: MotionConfig = MotionConfig(),
                 schedulerConfig: SchedulerConfig = SchedulerConfig(),
                 trackerConfig: TrackerConfig = TrackerConfig()) {
        self.motion = MotionDetector(config: motionConfig)
        self.scheduler = Scheduler(config: schedulerConfig)
        self.tracker = Tracker(config: trackerConfig)
        self.policy = FirePolicy(limits: fireLimits)
        self.aimer = Aimer(calibration: calibration, limits: limits)
    }

    /// What the policy has already spent, for persisting across a restart.
    public var shotLog: [ShotRecord] { policy.shotLog }

    /// Puts a persisted budget back. See `FirePolicy.restore(_:now:uptime:)`.
    public func restoreShotLog(_ records: [ShotRecord], now: Date, uptime: TimeInterval) {
        policy.restore(records, now: now, uptime: uptime)
    }

    /// Replaces the calibration, for instance right after the owner adds a point in the
    /// web UI.
    public func update(calibration: Calibration, limits: AimLimits = AimLimits()) {
        aimer = Aimer(calibration: calibration, limits: limits)
    }

    /// - Parameters:
    ///   - frame: the small grayscale frame motion detection runs on.
    ///   - detector: what the detector has to say about this moment. Most cycles carry
    ///     `.pending`, because detection answers a cycle or two after the crops that
    ///     produced it; passing `.answer([], capturedAt:)` instead would tell the tracker
    ///     that the detector looked and saw nothing, which counts against confirmation.
    ///   - status: the newest device status, or nil when the link's health is in doubt.
    ///   - now: wall clock, for the active-hours window.
    ///   - uptime: monotonic, for every interval this package measures.
    public func process(frame: GrayFrame,
                        detector: DetectorReport,
                        status: DeviceStatus?,
                        now: Date,
                        uptime: TimeInterval) -> CycleOutput {
        let blobs = motion.process(frame)
        let requests = scheduler.next(blobs: blobs)
        let tracks = tracker.update(accepted(detector), asOf: uptime)

        var solutions: [Int: AimSolution] = [:]
        if let aimer {
            for track in tracks {
                solutions[track.id] = aimer.solve(for: track)
            }
        }

        let decision = policy.decide(PolicyInput(
            mode: mode,
            tracks: tracks,
            solutions: solutions,
            masks: masks,
            status: status,
            meanLuma: frame.meanLuma,
            now: now,
            uptime: uptime
        ))

        return CycleOutput(decision: decision, cropRequests: requests, tracks: tracks,
                           solutions: solutions, blobs: blobs, meanLuma: frame.meanLuma,
                           refusal: policy.lastRefusal,
                           shotsThisHour: policy.shotsInLastHour(asOf: uptime))
    }

    /// Detector answers can overtake each other whenever the app keeps more than one
    /// request in flight. An answer older than one already applied would rewind every
    /// track it touches, so it is dropped instead: losing one look costs a fraction of a
    /// second of confirmation, where a rewind corrupts position, speed, stillness and the
    /// association gate at once. A non-finite capture time is dropped for the same reason.
    private func accepted(_ report: DetectorReport) -> DetectorReport {
        guard case .answer(_, let capturedAt) = report else { return report }
        guard capturedAt.isFinite else { return .pending }
        if let last = lastAnswerAt, capturedAt < last { return .pending }
        lastAnswerAt = capturedAt
        return report
    }
}
