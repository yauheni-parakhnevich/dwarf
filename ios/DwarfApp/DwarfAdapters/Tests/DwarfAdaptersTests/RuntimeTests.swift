import XCTest
import CoreVideo
import DwarfCore
@testable import DwarfAdapters

final class RuntimeTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private struct Rig {
        let runtime: Runtime
        let detector: FakeDetector
        let transport: FakeTransport
        let link: ActuatorLink
        let clock: TestClock
        let battery: FakeBattery
        let store: Store
    }

    /// A calibration dense enough for the Aimer to fit, covering the lower half of the
    /// frame where the ground is.
    private func calibration() -> Calibration {
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                points.append(CalibrationPoint(image: Point(x: x, y: y),
                                               pan: (x - 0.5) * 100,
                                               tilt: 30 - 34 * y,
                                               rangeM: 8 - 6 * y))
            }
        }
        return Calibration(points: points,
                           heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4),
                                           HeightOffsetSample(rangeM: 6, deltaTiltDeg: 2)])
    }

    private func makeRig(mode: Mode = .live) throws -> Rig {
        let store = Store(directory: directory)
        store.settings.mode = mode
        store.calibration = calibration()

        let clock = TestClock()
        // Noon in June, inside the active window.
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15; components.hour = 12
        clock.now = Calendar.current.date(from: components)!

        let transport = FakeTransport()
        transport.isConnected = true
        // One clock for the whole rig. The link stamps arriving statuses with it and the
        // runtime asks about uptimes from it; two clocks is exactly the defect the review
        // of Task 8 found, where a single rewind withheld every status forever.
        let steady = SteadyClock(wrapping: clock)
        let link = ActuatorLink(transport: transport, clock: steady)
        let detector = FakeDetector()
        let battery = FakeBattery()

        let runtime = Runtime(
            store: store,
            link: link,
            detector: detector,
            geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080), quarterTurns: 0),
            power: PowerManager(battery: battery),
            clock: steady)

        return Rig(runtime: runtime, detector: detector, transport: transport, link: link,
                   clock: clock, battery: battery, store: store)
    }

    private func brightBuffer() -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(kCFAllocatorDefault, 1920, 1080,
                            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &buffer)
        let pixels = buffer!
        CVPixelBufferLockBaseAddress(pixels, [])
        let y = CVPixelBufferGetBaseAddressOfPlane(pixels, 0)!
        for row in 0..<1080 {
            memset(y.advanced(by: row * CVPixelBufferGetBytesPerRowOfPlane(pixels, 0)), 120, 1920)
        }
        let uv = CVPixelBufferGetBaseAddressOfPlane(pixels, 1)!
        for row in 0..<540 {
            memset(uv.advanced(by: row * CVPixelBufferGetBytesPerRowOfPlane(pixels, 1)), 128, 1920)
        }
        CVPixelBufferUnlockBaseAddress(pixels, [])
        return pixels
    }

    /// The link timestamps this from the clock, so the caller sets `rig.clock.uptime`
    /// first, exactly as the real transport's callback would arrive mid-cycle.
    private func healthyStatus(in rig: Rig) {
        rig.transport.deliver(Data("""
        {"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":true,"charge":false,\
        "fan":false,"temp":22,"fault":null,"shots":0}\n
        """.utf8))
    }

    func testACycleWithNoAnswerYetIsPendingNotAnEmptyAnswer() throws {
        // The contract bullet that, when broken, leaves the whole system green and inert.
        let rig = try makeRig()
        rig.detector.next = []

        rig.clock.uptime = 0
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertEqual(rig.runtime.snapshot.lastReportWasPending, true,
                       "no detector answer had come back, so the tracker must not be told the detector looked")
    }

    func testAnAnswerIsTimestampedWithItsFrameNotItsArrival() throws {
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.6, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        rig.clock.uptime = 10
        rig.runtime.handle(frame: brightBuffer())   // asks
        rig.runtime.waitForDetector()
        rig.clock.uptime = 10.4
        rig.runtime.handle(frame: brightBuffer())   // collects

        XCTAssertEqual(try XCTUnwrap(rig.runtime.snapshot.lastAnswerCapturedAt), 10, accuracy: 1e-9,
                       "the box came from the frame captured at 10, not from the one at 10.4")
    }

    func testAnIntermittentDetectorStillGetsAShotOff() throws {
        // End to end, through every real component except the radio and the model: a
        // motionless cat, a detector that answers roughly every third cycle, and a shot.
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        let shots = rig.transport.sentStrings.filter { $0.contains("\"shoot\"") }
        XCTAssertFalse(shots.isEmpty, "expected at least one shoot: \(Set(rig.transport.sentStrings))")
    }

    func testADryRunNeverReachesTheNozzle() throws {
        let rig = try makeRig(mode: .dryRun)
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        XCTAssertTrue(rig.transport.sentStrings.allSatisfy { !$0.contains("\"shoot\"") },
                      "a dry run that fires is worse than no dry run at all")
        XCTAssertGreaterThan(rig.runtime.snapshot.wouldShootCount, 0, "but it must still record what it would have done")
    }

    func testNoShotWithoutAFreshStatus() throws {
        // The status is never delivered, so FirePolicy is handed nil every cycle.
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        XCTAssertTrue(rig.transport.sentStrings.allSatisfy { !$0.contains("\"shoot\"") })
    }

    func testCriticalHeatDisarmsAndStopsLooking() throws {
        let rig = try makeRig()
        rig.runtime.thermalOverride = .critical
        rig.clock.uptime = 1
        healthyStatus(in: rig)
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertTrue(rig.transport.sentStrings.contains { $0.contains("\"arm\"") && $0.contains("false") })
        XCTAssertEqual(rig.detector.calls, 0, "nothing should be asked of the model while it is this hot")
    }

    func testTheDisarmIsSentOnceNotAtFrameRate() throws {
        let rig = try makeRig()
        rig.runtime.thermalOverride = .critical

        for i in 0..<30 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
        }

        let disarms = rig.transport.sentStrings.filter { $0.contains("\"arm\"") }
        XCTAssertEqual(disarms.count, 1, "the firmware latches it; repeating is noise: \(disarms.count)")
    }

    func testTheSchedulerIsToldTheRealFrameSize() throws {
        // A contract bullet: crop rectangles are fractions of a frame whose size only the
        // app knows.
        let rig = try makeRig()
        XCTAssertEqual(rig.runtime.schedulerConfig.frameWidthPixels, 1920)
        XCTAssertEqual(rig.runtime.schedulerConfig.frameHeightPixels, 1080)
    }

    func testAFailingDetectorDoesNotStopTheLoop() throws {
        struct Broken: Error {}
        let rig = try makeRig()
        rig.detector.error = Broken()

        rig.clock.uptime = 1
        rig.runtime.handle(frame: brightBuffer())
        rig.runtime.waitForDetector()
        rig.clock.uptime = 1.2
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertGreaterThan(rig.runtime.snapshot.detectorFailures, 0)
        XCTAssertEqual(rig.runtime.snapshot.lastReportWasPending, true, "a failed inference is not evidence of absence")
    }

    func testTheTrackerIsSizedAgainstWhatThisPhoneCanActuallyDetect() throws {
        // M0 measured 0.30 s an inference. One answer can carry three of them, and with a
        // two-tile sweep an animal the sweep alone finds is looked at roughly every 1.8 s.
        // DwarfCore's 1 s stillWindow would let every sample age out between hits, so a cat
        // sitting in plain view would be tracked perfectly and never fired at.
        let rig = try makeRig()
        XCTAssertGreaterThan(rig.runtime.trackerConfig.stillWindow, 1.8,
                             "a still cat must have two samples alive at once")
        XCTAssertEqual(rig.runtime.trackerConfig.confirmWindow, 4,
                       "three oscillates against the sweep's alternating hit and miss")
    }
}

