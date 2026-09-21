import XCTest
@testable import DwarfCore

final class CycleTests: XCTestCase {
    private func noon() -> Date {
        var c = DateComponents()
        c.year = 2026; c.month = 6; c.day = 15; c.hour = 12
        return Calendar.current.date(from: c)!
    }

    private func brightFrame(width: Int = 40, height: Int = 30) -> GrayFrame {
        GrayFrame(width: width, height: height, pixels: [UInt8](repeating: 120, count: width * height))
    }

    private func darkFrame(width: Int = 40, height: Int = 30) -> GrayFrame {
        GrayFrame(width: width, height: height, pixels: [UInt8](repeating: 5, count: width * height))
    }

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

    private func healthyStatus() -> DeviceStatus {
        DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: true, pump: true,
                     charge: false, fan: false, temp: 22, fault: nil, shots: 0)
    }

    private func cat(x: Double = 0.5, y: Double = 0.72) -> Detection {
        Detection(box: Rect(x: x - 0.04, y: y - 0.06, width: 0.08, height: 0.06), confidence: 0.9)
    }

    func testAlwaysAsksForSomethingToLookAt() {
        let cycle = Cycle(calibration: calibration())
        let output = cycle.process(frame: brightFrame(), detections: [], status: healthyStatus(),
                                   now: noon(), uptime: 0)
        XCTAssertFalse(output.cropRequests.isEmpty, "the sweep runs even with nothing moving")
    }

    func testAStillConfirmedCatEventuallyGetsShot() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .live   // Cycle defaults to dry-run, deliberately
        var uptime = 0.0
        var decisions: [FireDecision] = []

        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            decisions.append(output.decision)
            uptime += 0.1
        }

        XCTAssertTrue(decisions.contains { if case .shoot = $0 { return true } else { return false } },
                      "a confirmed, still cat in range should be fired at: \(decisions)")
    }

    func testDarknessSuppressesEverything() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .live
        var uptime = 0.0
        for _ in 0..<15 {
            let output = cycle.process(frame: darkFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            XCTAssertEqual(output.decision, .none)
            uptime += 0.1
        }
    }

    func testTracksAreExposedForTheUI() {
        let cycle = Cycle(calibration: calibration())
        let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                   status: healthyStatus(), now: noon(), uptime: 0)
        XCTAssertEqual(output.tracks.count, 1)
        XCTAssertEqual(output.solutions.count, 1)
    }

    func testWithoutCalibrationItStillTracksButNeverFires() {
        // An uncalibrated gnome must still run, otherwise it could never be calibrated.
        let cycle = Cycle(calibration: .empty)
        cycle.mode = .live

        var uptime = 0.0
        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            XCTAssertFalse(output.tracks.isEmpty, "tracking works without calibration")
            XCTAssertTrue(output.solutions.isEmpty, "but there are no aim solutions")
            if case .shoot = output.decision { XCTFail("fired without calibration") }
            uptime += 0.1
        }
    }

    func testModeIsRespected() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .dryRun
        var uptime = 0.0
        var sawWouldShoot = false

        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            if case .wouldShoot = output.decision { sawWouldShoot = true }
            if case .shoot = output.decision { XCTFail("dry-run must not fire") }
            uptime += 0.1
        }
        XCTAssertTrue(sawWouldShoot)
    }
}
