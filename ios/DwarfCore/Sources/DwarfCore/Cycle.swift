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

    /// Replaces the calibration, for instance right after the owner adds a point in the
    /// web UI.
    public func update(calibration: Calibration, limits: AimLimits = AimLimits()) {
        aimer = Aimer(calibration: calibration, limits: limits)
    }

    public func process(frame: GrayFrame,
                        detections: [Detection],
                        status: DeviceStatus?,
                        now: Date,
                        uptime: TimeInterval) -> CycleOutput {
        let blobs = motion.process(frame)
        let requests = scheduler.next(blobs: blobs)
        let tracks = tracker.update(detections: detections, at: uptime)

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
                           solutions: solutions, blobs: blobs, meanLuma: frame.meanLuma)
    }
}
