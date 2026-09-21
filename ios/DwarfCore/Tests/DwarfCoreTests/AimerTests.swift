import XCTest
@testable import DwarfCore

final class AimerTests: XCTestCase {
    /// A synthetic but plausible yard: pan follows x, tilt and range follow y.
    private func calibration(withHeightOffsets: Bool = true) -> Calibration {
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                let range = 8.0 - 6.0 * y          // y 0.55 -> 4.7 m, y 0.95 -> 2.3 m
                points.append(CalibrationPoint(
                    image: Point(x: x, y: y),
                    pan: (x - 0.5) * 100,          // -40 .. +40 degrees
                    tilt: 30 - 34 * y,             // further away means higher tilt
                    rangeM: range
                ))
            }
        }
        return Calibration(
            points: points,
            heightOffsets: withHeightOffsets
                ? [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4.0),
                   HeightOffsetSample(rangeM: 6, deltaTiltDeg: 2.0)]
                : []
        )
    }

    private func track(ground: Point, headOffsetY: Double = 0.06) -> Track {
        Track(id: 1,
              box: Rect(x: ground.x - 0.04, y: ground.y - headOffsetY, width: 0.08, height: headOffsetY),
              confidence: 0.9, lastSeen: 0, isConfirmed: true, isStill: true, isAmbiguous: false)
    }

    func testRefusesToBuildWithoutEnoughPoints() {
        let thin = Calibration(points: Array(calibration().points.prefix(5)))
        XCTAssertNil(Aimer(calibration: thin))
    }

    func testRecoversPanAndRange() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let solution = aimer.solve(for: track(ground: Point(x: 0.7, y: 0.75)))

        XCTAssertEqual(solution.pan, 20, accuracy: 1.5)
        XCTAssertEqual(solution.rangeM, 3.5, accuracy: 0.2)
        XCTAssertFalse(solution.isFlagged)
    }

    func testCloseRangeAimsAtTheBody() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.92)))   // ~2.5 m

        XCTAssertEqual(solution.target, .body)
        // Body aim is the ground solution with no height offset added.
        XCTAssertEqual(solution.tilt, 30 - 34 * 0.92, accuracy: 1.0)
    }

    func testLongRangeAimsAtTheHeadAndAddsTheHeightOffset() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let ground = Point(x: 0.5, y: 0.6)                                        // ~4.4 m
        let solution = aimer.solve(for: track(ground: ground))

        XCTAssertEqual(solution.target, .head)
        let groundTilt = 30 - 34 * 0.6
        let expectedOffset = try XCTUnwrap(calibration().heightOffset(atRange: solution.rangeM))
        XCTAssertEqual(solution.tilt, groundTilt + expectedOffset, accuracy: 1.0)
        XCTAssertGreaterThan(solution.tilt, groundTilt, "head aim must sit above ground aim")
    }

    func testHeadAimIsFlaggedWithoutAHeightOffsetTable() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration(withHeightOffsets: false)))
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.6)))

        XCTAssertEqual(solution.target, .head)
        XCTAssertTrue(solution.isFlagged, "no height data means the head solution is a guess")
    }

    func testSolutionsOutsideTheServoLimitsAreFlaggedAndClamped() throws {
        var limits = AimLimits()
        limits.panMax = 10
        let aimer = try XCTUnwrap(Aimer(calibration: calibration(), limits: limits))
        let solution = aimer.solve(for: track(ground: Point(x: 0.9, y: 0.8)))

        XCTAssertTrue(solution.isFlagged)
        XCTAssertLessThanOrEqual(solution.pan, 10)
    }

    func testPointsFarOutsideTheCalibratedAreaAreFlagged() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        // Calibration covers y 0.55...0.95; the top of the frame is the sky.
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.15)))
        XCTAssertTrue(solution.isFlagged)
    }

    func testResidualsReportPerPointError() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let residuals = aimer.residuals()

        XCTAssertEqual(residuals.count, calibration().points.count)
        // The synthetic yard is exactly quadratic, so the fit should be near-perfect.
        XCTAssertLessThan(residuals.map(\.panError).max() ?? 99, 0.5)
        XCTAssertLessThan(residuals.map(\.tiltError).max() ?? 99, 0.5)
    }
}
