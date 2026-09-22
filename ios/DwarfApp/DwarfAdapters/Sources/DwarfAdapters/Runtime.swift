import Foundation
import CoreVideo
import DwarfCore

/// The loop. Owns the `Cycle` and is the only thing that knows about every adapter at once.
///
/// Most of what follows is `ios/DwarfCore/README.md`'s "contract this package cannot
/// enforce", made into code. The two that matter most:
///
/// - Detection is asynchronous. A cycle with no answer back yet reports `.pending`, never an
///   empty answer, because an empty answer means "the detector looked and saw nothing" and
///   counts against confirmation. Report those and a perfectly detected cat never confirms.
/// - An answer is timestamped with when its **frame** was captured, not when it came back.
///   Stillness gates firing, and a late answer at the current time makes a moving animal
///   look stiller than it is.
public final class Runtime {
    private let store: Store
    private let link: ActuatorLink
    private let detector: Detector
    private let converter: FrameConverter
    private let power: PowerManager
    private let clock: Clock
    private let cycle: Cycle

    private let detectorQueue = DispatchQueue(label: "garden.dwarf.detector")
    private var detectorBusy = false
    /// An answer that has come back and has not been handed to the tracker yet.
    private var pendingAnswer: (detections: [Detection], capturedAt: TimeInterval)?
    private let lock = NSLock()

    private var cycleCounter = 0

    /// Immutable after init, so they need no guarding.
    public let schedulerConfig: SchedulerConfig
    public let trackerConfig: TrackerConfig

    private var state = RuntimeSnapshot()
    private var pendingMode: Mode?
    private var pendingCalibration: Calibration?

    /// One consistent view of what the runtime last did, for a screen or a log.
    ///
    /// A snapshot rather than a handful of properties, and taken under the lock, because
    /// the alternative was demonstrably unsafe: every `public private(set)` field used to be
    /// read without synchronisation from whatever queue the UI happened to be on, while the
    /// capture queue wrote them. ThreadSanitizer found real races on that surface, and an
    /// uninstrumented build of the same scenario segfaulted inside ARC — a reader holding a
    /// half-assigned `CycleOutput` while its arrays were released underneath it. Six
    /// separate fields could also disagree with each other mid-cycle; one value cannot.
    public var snapshot: RuntimeSnapshot {
        lock.lock()
        defer { lock.unlock() }
        return state
    }

    /// How many previously spent shots this pipeline started life already knowing about.
    /// Zero on a clean install, and on any run where the last one fired nothing.
    public private(set) var restoredShots = 0

    /// Set in tests; production reads `ProcessInfo`.
    public var thermalOverride: ProcessInfo.ThermalState?

    public init(store: Store, link: ActuatorLink, detector: Detector, geometry: FrameGeometry,
                power: PowerManager, clock: Clock) {
        self.store = store
        self.link = link
        self.detector = detector
        self.power = power
        self.clock = clock
        self.converter = FrameConverter(geometry: geometry)

        // The one place SchedulerConfig learns how big the frame really is. A remembered
        // constant here means crops cut from the wrong part of the garden.
        var config = SchedulerConfig()
        config.cropPixels = store.settings.modelSide
        geometry.apply(to: &config)
        self.schedulerConfig = config

        // The tracker counts its windows in detector answers, not in frames, so they have
        // to be sized against what this phone's model actually does. M0 measured 0.30 s an
        // inference. A cycle can ask for two motion crops and a sweep tile, so one answer
        // can take three of those -- 0.9 s -- and with the sweep split in two tiles, an
        // animal the sweep alone finds is looked at every other answer, about 1.8 s apart.
        //
        // DwarfCore's default stillWindow is 1.0 s and samples are only recorded on a hit,
        // so each would age out before the next arrived and isStill could never become
        // true: a cat sitting in plain view while anything else in frame moved would be
        // tracked perfectly and never fired at. The default confirmWindow of 3 also
        // oscillates against the sweep's alternating hit and miss.
        var tracker = TrackerConfig()
        let answerInterval = store.settings.detectorLatency * Double(config.maxMotionCrops + 1)
        let sweepRevisit = answerInterval * Double(config.sweepColumns * config.sweepRows)
        tracker.stillWindow = max(tracker.stillWindow, sweepRevisit * 1.4)
        tracker.confirmWindow = 4
        self.trackerConfig = tracker

        self.cycle = Cycle(calibration: store.calibration, schedulerConfig: config,
                           trackerConfig: tracker)
        // Hand back what the last run already spent. Without this the caps were a property
        // of one run of one process: rebuilding the pipeline — which the mount-orientation
        // button on the screen does — gave the animal in front of the gnome a fresh
        // allowance, and so did relaunching the app.
        self.cycle.restoreShotLog(store.shotLog, now: clock.now, uptime: clock.uptime)
        self.restoredShots = self.cycle.shotLog.count
        self.cycle.masks = store.masks
        self.cycle.mode = store.settings.mode
    }

    /// Call once per camera frame, on the capture queue.
    public func handle(frame pixelBuffer: CVPixelBuffer) {
        applyPendingUpdates()

        let uptime = clock.uptime
        link.tick(uptime: uptime)

        guard let gray = converter.gray(from: pixelBuffer) else { return }

        let thermal = thermalOverride ?? ProcessInfo.processInfo.thermalState
        let status = link.status(asOf: uptime)
        let decision = power.evaluate(thermal: thermal, meanLuma: gray.meanLuma,
                                      ambientC: status?.temp, uptime: uptime)
        apply(decision, at: uptime)
        mutate {
            $0.paused = decision.pauseDetection
            $0.cycleDivisor = decision.cycleDivisor
            $0.lumaUnusable = decision.lumaUnusable
            $0.meanLuma = gray.meanLuma
            $0.status = status
        }

        // Paused is a state worth seeing, so it is recorded above before returning. The
        // decision and tracks deliberately keep their last values rather than being
        // cleared: what the gnome was doing when it stopped is the useful part.
        if decision.pauseDetection { return }
        cycleCounter += 1
        if decision.cycleDivisor > 1, cycleCounter % decision.cycleDivisor != 0 { return }

        let report = collectAnswer()
        let pending = { if case .pending = report { return true } else { return false } }()
        mutate { $0.lastReportWasPending = pending }

        let output = cycle.process(frame: gray,
                                   detector: report,
                                   status: status,
                                   now: clock.now,
                                   uptime: uptime)
        recordCycleRate(at: uptime)
        mutate {
            $0.decision = output.decision
            $0.refusal = output.refusal
            $0.tracks = output.tracks
            $0.solutions = output.solutions
            $0.cropRequests = output.cropRequests
            $0.blobs = output.blobs
            $0.meanLuma = output.meanLuma
            $0.shotsThisHour = output.shotsThisHour
            $0.status = status
            $0.deviceRefusals = self.link.refusals
            $0.clockAnomalies = (self.clock as? SteadyClock)?.anomalies ?? 0
        }
        carryOut(output.decision)
        askDetector(about: output.cropRequests, from: pixelBuffer, capturedAt: uptime)
    }

    /// Replaces the calibration after the owner records a point.
    ///
    /// Queued rather than applied here. `Cycle`, `FirePolicy` and `Store` are all plain
    /// mutable state with no locks of their own, so touching them from a settings screen
    /// while a frame is being processed on the capture queue is the same race as the one
    /// the snapshot above exists to close. Taking a lock around them instead would deadlock
    /// against `askDetector`, which already holds it. Queuing means everything that touches
    /// the pipeline happens on one queue, which is the property that actually makes this
    /// class safe rather than merely lock-decorated.
    public func update(calibration: Calibration) {
        lock.lock()
        pendingCalibration = calibration
        lock.unlock()
    }

    public func update(mode: Mode) {
        lock.lock()
        pendingMode = mode
        lock.unlock()
    }

    private var frameTimes: [TimeInterval] = []
    private var answerTimes: [TimeInterval] = []

    /// Rates measured over a rolling ten seconds. Configured numbers describe intent;
    /// these describe what the phone is actually managing, which after a thermal backoff
    /// or under a slow model is a different thing entirely.
    private func recordCycleRate(at uptime: TimeInterval) {
        frameTimes.append(uptime)
        frameTimes.removeAll { uptime - $0 > 10 }
        let frames = Double(frameTimes.count)
        let answers = Double(answerTimes.count)
        mutate {
            $0.framesPerSecond = frames / 10
            $0.answersPerSecond = answers / 10
        }
    }

    private func applyPendingUpdates() {
        lock.lock()
        let mode = pendingMode
        let calibration = pendingCalibration
        pendingMode = nil
        pendingCalibration = nil
        lock.unlock()

        if let mode {
            store.settings.mode = mode
            cycle.mode = mode
        }
        if let calibration {
            store.calibration = calibration
            cycle.update(calibration: calibration)
        }

        // Persisted here, on the capture queue, immediately after the change lands. Saving
        // from wherever the setting was changed instead read `store` from another queue
        // while this method wrote it, and — because the write happens a frame later — wrote
        // the *previous* mode to disk. A gnome switched to live and restarted within the
        // same tenth of a second came back in dry-run, which is exactly what
        // `Settings.mode` promises will not happen.
        if mode != nil || calibration != nil {
            try? store.save()
        }
    }

    // MARK: detection

    private func collectAnswer() -> DetectorReport {
        lock.lock()
        defer { lock.unlock() }
        guard let answer = pendingAnswer else { return .pending }
        pendingAnswer = nil
        state.lastAnswerCapturedAt = answer.capturedAt
        return .answer(answer.detections, capturedAt: answer.capturedAt)
    }

    private func askDetector(about requests: [CropRequest], from pixelBuffer: CVPixelBuffer,
                             capturedAt: TimeInterval) {
        guard !requests.isEmpty else { return }
        lock.lock()
        let busy = detectorBusy
        if busy {
            // The sweep's round-robin advanced anyway, inside Cycle, so a detector that
            // cannot keep up does not merely answer late — it silently skips most of the
            // rotation. Counted so that is visible rather than inferred.
            state.droppedRequests += 1
        } else {
            detectorBusy = true
            state.detectorBusySince = capturedAt
        }
        lock.unlock()
        guard !busy else { return }

        // The inputs are cut on this queue, while the buffer is still guaranteed valid. The
        // capture system reuses its buffers, and a CVPixelBuffer held past the delegate call
        // is a buffer whose contents change underneath the model.
        let side = store.settings.modelSide
        let inputs: [(CVPixelBuffer, PixelRect)] = requests.compactMap { request in
            guard let rect = converter.geometry.validPixelRect(of: request.rect),
                  let input = converter.modelInput(from: pixelBuffer, cropInFrame: rect, side: side)
            else { return nil }
            return (input, rect)
        }
        guard !inputs.isEmpty else {
            lock.lock(); detectorBusy = false; lock.unlock()
            return
        }

        detectorQueue.async { [weak self] in
            guard let self else { return }
            var detections: [Detection] = []
            var failed = false

            for (input, rect) in inputs {
                do {
                    let boxes = try self.detector.detect(input: input)
                    let letterbox = Letterbox(crop: rect, side: side)
                    for box in boxes {
                        let frameBox = letterbox.frameBox(fromModel: box.box, crop: rect,
                                                          frame: self.converter.geometry.frame)
                        detections.append(Detection(box: frameBox, confidence: box.confidence))
                    }
                } catch {
                    failed = true
                }
            }

            self.lock.lock()
            if failed {
                self.state.detectorFailures += 1
            }
            // A failed inference is not evidence of absence, so nothing is handed over and
            // the next cycle reports pending.
            if !failed {
                self.pendingAnswer = (detections, capturedAt)
                self.answerTimes.append(capturedAt)
                self.answerTimes.removeAll { capturedAt - $0 > 10 }
            }
            self.detectorBusy = false
            self.state.detectorBusySince = nil
            self.lock.unlock()
        }
    }

    /// Blocks until the detector queue has drained. Tests only.
    public func waitForDetector() {
        detectorQueue.sync {}
    }

    // MARK: acting

    private func carryOut(_ decision: FireDecision) {
        switch decision {
        case .none:
            break
        case .aim(let pan, let tilt):
            send(.aim(pan: pan, tilt: tilt))
        case .park:
            send(.park)
        case .shoot(let pan, let tilt, let ms):
            // The only place in the app allowed to turn a decision into water.
            send(.shoot(pan: pan, tilt: tilt, ms: ms))
            persistShotLog()
        case .wouldShoot:
            // Deliberately not sent. A dry run that fires is worse than no dry run.
            // The budget is still spent and still recorded, because a dry run whose log
            // does not predict live behaviour is worthless.
            mutate { $0.wouldShootCount += 1 }
            persistShotLog()
        }
    }

    /// Written after every shot, live or dry-run, because the budget it protects is spent
    /// at that moment and a crash a second later must not refund it.
    private func persistShotLog() {
        store.shotLog = cycle.shotLog
        try? store.save()
        mutate { $0.saveFailures = self.store.saveFailures }
    }

    /// `try?` at every send site means a shot the policy genuinely authorised can fail to
    /// leave the phone with no trace at all. The firmware's watchdog still protects the
    /// animal, so this is bookkeeping rather than safety, but "did the shot actually go
    /// out" should be answerable.
    private func send(_ command: Command) {
        do {
            try link.send(command)
        } catch {
            mutate { $0.sendFailures += 1 }
        }
    }

    private func mutate(_ change: (inout RuntimeSnapshot) -> Void) {
        lock.lock()
        change(&state)
        lock.unlock()
    }

    private func apply(_ decision: PowerDecision, at uptime: TimeInterval) {
        // Once, on the way into critical, not ten times a second for as long as it lasts.
        // The gnome stays disarmed because the firmware latches it, and a command repeated
        // at frame rate is a radio kept busy for nothing while the phone is already too hot.
        if decision.disarm != lastDisarm {
            lastDisarm = decision.disarm
            if decision.disarm { send(.arm(false)) }
        }
        if decision.charger != lastCharger {
            lastCharger = decision.charger
            send(.charge(decision.charger))
        }
        if decision.fan != lastFan {
            lastFan = decision.fan
            send(.fan(decision.fan))
        }
    }

    private var lastCharger: Bool?
    private var lastFan: Bool?
    private var lastDisarm: Bool?
}

/// One consistent view of what the runtime last did.
///
/// Every field is a value type, copied out under the lock in a single read, so a reader on
/// another queue gets a coherent picture rather than six fields that may disagree with each
/// other — or, as it was before, a `CycleOutput` being released underneath it mid-assignment.
public struct RuntimeSnapshot: Sendable {
    public var decision: FireDecision = .none
    /// Why the best candidate was not fired at. The question an owner actually asks.
    public var refusal: FireRefusal?
    public var tracks: [Track] = []
    /// The aim computed for each track, so a screen can show where the gnome believes an
    /// animal is standing and how far away, not merely that it sees one.
    public var solutions: [Int: AimSolution] = [:]
    public var cropRequests: [CropRequest] = []
    public var blobs: [Blob] = []
    public var meanLuma: Double = 0
    public var lumaUnusable = false
    public var shotsThisHour = 0
    /// What the gnome last said about itself, or nil when nothing fresh has arrived.
    public var status: DeviceStatus?
    /// Measured, not configured: how many frames a second are really being processed, and
    /// how many detector answers a second are really landing. The second number is the one
    /// the tracker's windows have to be sized against.
    public var framesPerSecond: Double = 0
    public var answersPerSecond: Double = 0
    /// Detection paused, and the cycle rate halved, by heat or darkness.
    public var paused = false
    public var cycleDivisor = 1
    /// Times the monotonic clock misbehaved. A phone whose clock jumps has a bigger problem.
    public var clockAnomalies = 0
    /// Commands the gnome itself refused, by reason, from its acks.
    public var deviceRefusals: [String: Int] = [:]
    /// Capture time of the newest detector answer the tracker has been given, or nil when
    /// none has ever landed.
    public var lastAnswerCapturedAt: TimeInterval?
    public var lastReportWasPending = true
    public var wouldShootCount = 0
    public var detectorFailures = 0
    /// Commands the policy authorised that failed to reach the gnome.
    public var sendFailures = 0
    /// Writes to disk that failed. A setting, a calibration or a spent shot budget that
    /// never reached the disk is a promise quietly broken.
    public var saveFailures = 0
    /// Crop requests skipped because the detector was still busy with the previous ones.
    /// A steadily climbing count means the model cannot keep up with the cycle rate, which
    /// starves the sweep and, past a point, stops still animals ever being confirmed.
    public var droppedRequests = 0
    /// Capture time of the answer the detector is working on, or nil when it is idle.
    /// There is no timeout around a CoreML call and none can be added — it cannot be
    /// cancelled — so a model that hangs would otherwise stop all detection for good with
    /// no symptom but tracks quietly ageing out. A value here that stops changing is that
    /// symptom.
    public var detectorBusySince: TimeInterval?

    public init() {}
}
