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

    public private(set) var schedulerConfig = SchedulerConfig()
    public private(set) var lastReportWasPending = true
    public private(set) var lastAnswerCapturedAt: TimeInterval?
    public private(set) var wouldShootCount = 0
    public private(set) var detectorFailures = 0
    public private(set) var lastOutput: CycleOutput?
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

        self.cycle = Cycle(calibration: store.calibration, schedulerConfig: config)
        self.cycle.masks = store.masks
        self.cycle.mode = store.settings.mode
    }

    /// Call once per camera frame, on the capture queue.
    public func handle(frame pixelBuffer: CVPixelBuffer) {
        let uptime = clock.uptime
        link.tick(uptime: uptime)

        guard let gray = converter.gray(from: pixelBuffer) else { return }

        let thermal = thermalOverride ?? ProcessInfo.processInfo.thermalState
        let decision = power.evaluate(thermal: thermal, meanLuma: gray.meanLuma, uptime: uptime)
        apply(decision, at: uptime)

        if decision.pauseDetection { return }
        cycleCounter += 1
        if decision.cycleDivisor > 1, cycleCounter % decision.cycleDivisor != 0 { return }

        let report = collectAnswer()
        lastReportWasPending = { if case .pending = report { return true } else { return false } }()

        let output = cycle.process(frame: gray,
                                   detector: report,
                                   status: link.status(asOf: uptime),
                                   now: clock.now,
                                   uptime: uptime)
        lastOutput = output
        carryOut(output.decision)
        askDetector(about: output.cropRequests, from: pixelBuffer, capturedAt: uptime)
    }

    /// Replaces the calibration after the owner records a point.
    public func update(calibration: Calibration) {
        store.calibration = calibration
        cycle.update(calibration: calibration)
    }

    public func update(mode: Mode) {
        store.settings.mode = mode
        cycle.mode = mode
    }

    // MARK: detection

    private func collectAnswer() -> DetectorReport {
        lock.lock()
        defer { lock.unlock() }
        guard let answer = pendingAnswer else { return .pending }
        pendingAnswer = nil
        lastAnswerCapturedAt = answer.capturedAt
        return .answer(answer.detections, capturedAt: answer.capturedAt)
    }

    private func askDetector(about requests: [CropRequest], from pixelBuffer: CVPixelBuffer,
                             capturedAt: TimeInterval) {
        guard !requests.isEmpty else { return }
        lock.lock()
        let busy = detectorBusy
        if !busy { detectorBusy = true }
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
                self.detectorFailures += 1
            }
            // A failed inference is not evidence of absence, so nothing is handed over and
            // the next cycle reports pending.
            if !failed {
                self.pendingAnswer = (detections, capturedAt)
            }
            self.detectorBusy = false
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
            try? link.send(.aim(pan: pan, tilt: tilt))
        case .park:
            try? link.send(.park)
        case .shoot(let pan, let tilt, let ms):
            // The only place in the app allowed to turn a decision into water.
            try? link.send(.shoot(pan: pan, tilt: tilt, ms: ms))
        case .wouldShoot:
            // Deliberately not sent. A dry run that fires is worse than no dry run.
            wouldShootCount += 1
        }
    }

    private func apply(_ decision: PowerDecision, at uptime: TimeInterval) {
        // Once, on the way into critical, not ten times a second for as long as it lasts.
        // The gnome stays disarmed because the firmware latches it, and a command repeated
        // at frame rate is a radio kept busy for nothing while the phone is already too hot.
        if decision.disarm != lastDisarm {
            lastDisarm = decision.disarm
            if decision.disarm { try? link.send(.arm(false)) }
        }
        if decision.charger != lastCharger {
            lastCharger = decision.charger
            try? link.send(.charge(decision.charger))
        }
        if decision.fan != lastFan {
            lastFan = decision.fan
            try? link.send(.fan(decision.fan))
        }
    }

    private var lastCharger: Bool?
    private var lastFan: Bool?
    private var lastDisarm: Bool?
}
