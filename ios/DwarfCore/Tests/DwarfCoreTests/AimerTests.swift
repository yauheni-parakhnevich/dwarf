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

    // MARK: - Body/head blending

    func testTiltBlendsContinuouslyAcrossTheBodyHeadBoundary() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        // Sweep from comfortably inside "body" range to comfortably inside "head" range in
        // small, equal steps. A hard switch at the split used to move the whole height
        // offset in a single step; a blended one should not move by noticeably more in any
        // one step than its neighbours do.
        var tilts: [Double] = []
        var y = 0.60
        while y <= 0.75 {
            let solution = aimer.solve(groundPoint: Point(x: 0.5, y: y), headPoint: Point(x: 0.5, y: y - 0.06))
            tilts.append(solution.tilt)
            y += 0.002
        }

        let deltas = zip(tilts, tilts.dropFirst()).map { abs($1 - $0) }
        let maxDelta = try XCTUnwrap(deltas.max())
        let avgDelta = deltas.reduce(0, +) / Double(deltas.count)

        // Every step covers the same amount of range, so a smooth blend should make every
        // delta roughly the same size - nothing should stick out as an order-of-magnitude
        // jump the way the old hard switch did (see the Task 7 analysis: ~3.34 degrees in
        // one step, about 20-25x its neighbours).
        XCTAssertLessThan(maxDelta, avgDelta * 3, "no single step should dominate a smooth blend")
        XCTAssertLessThan(maxDelta, 1.0)
    }

    func testHeadLabelSwitchesAtTheSplitWhileTiltKeepsBlending() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        // Below split - blend/2 (3.8 m): pure ground aim, no offset at all.
        let pureBody = aimer.solve(groundPoint: Point(x: 0.5, y: 0.75), headPoint: Point(x: 0.5, y: 0.69))
        XCTAssertEqual(pureBody.target, .body)
        XCTAssertEqual(pureBody.tilt, 30 - 34 * 0.75, accuracy: 0.05)

        // At or above split + blend/2 (4.2 m): the full offset, as before.
        let fullHead = aimer.solve(groundPoint: Point(x: 0.5, y: 0.6), headPoint: Point(x: 0.5, y: 0.54))
        XCTAssertEqual(fullHead.target, .head)
        let groundTiltAtFullHead = 30 - 34 * 0.6
        let fullOffset = try XCTUnwrap(calibration().heightOffset(atRange: fullHead.rangeM))
        XCTAssertEqual(fullHead.tilt, groundTiltAtFullHead + fullOffset, accuracy: 0.05)

        // Just above the split (4.001 m, comfortably clear of floating-point noise around
        // the exact boundary): target already reads .head, but the tilt only carries a
        // little over half the offset - that is expected, not a bug.
        let yJustAboveSplit = (8.0 - 4.001) / 6.0
        let midBand = aimer.solve(groundPoint: Point(x: 0.5, y: yJustAboveSplit),
                                   headPoint: Point(x: 0.5, y: yJustAboveSplit - 0.06))
        XCTAssertEqual(midBand.target, .head)
        let groundTiltAtMidBand = 30 - 34 * yJustAboveSplit
        let offsetAtMidBand = try XCTUnwrap(calibration().heightOffset(atRange: midBand.rangeM))
        let expectedFactor = (midBand.rangeM - 3.8) / 0.4
        XCTAssertGreaterThan(expectedFactor, 0.0)
        XCTAssertLessThan(expectedFactor, 1.0)
        XCTAssertEqual(midBand.tilt, groundTiltAtMidBand + expectedFactor * offsetAtMidBand, accuracy: 0.05)
    }

    // MARK: - Head point outside the calibrated area

    func testHeadSolutionIsFlaggedWhenTheHeadPointLeavesTheCalibratedArea() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        // The ground point is comfortably inside the calibrated area and gives a
        // head-range solution, but a badly stretched box (or two merged detections) puts
        // the head point far above the frame, well outside anything ever measured.
        let solution = aimer.solve(groundPoint: Point(x: 0.5, y: 0.6), headPoint: Point(x: 0.5, y: 0.3))

        XCTAssertEqual(solution.target, .head)
        XCTAssertTrue(solution.isFlagged)
        XCTAssertTrue(solution.flagReasons.contains("outside the calibrated area"))
    }

    // MARK: - Flag reason ranking

    func testFlagReasonsRankTheServoLimitAboveAMissingHeightOffset() throws {
        var limits = AimLimits()
        limits.panMax = 5
        let aimer = try XCTUnwrap(Aimer(calibration: calibration(withHeightOffsets: false), limits: limits))
        // Inside the calibrated area, head range, no height offset table, and a pan the
        // servo cannot reach: two reasons apply at once.
        let solution = aimer.solve(for: track(ground: Point(x: 0.9, y: 0.6)))

        XCTAssertEqual(solution.target, .head)
        XCTAssertTrue(solution.isFlagged)
        XCTAssertEqual(solution.flagReason, "outside servo limits", "the servo limit is the more serious problem")
        XCTAssertEqual(solution.flagReasons, ["outside servo limits", "no height offset calibrated"])
    }

    // MARK: - Head-point pan with a yard where pan actually couples with height

    func testHeadPanUsesTheHeadPointWhenPanCouplesWithFrameHeight() throws {
        // The plan's synthetic yard makes pan a pure function of x, so it cannot tell
        // whether using the head point for pan (rather than the ground point) matters. A
        // real camera's pan-per-pixel does couple with vertical position near the frame
        // edges (parallax / lens distortion); model that coupling here so the design
        // decision is actually exercised.
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                let range = 8.0 - 6.0 * y
                let pan = (x - 0.5) * 100 + 15 * (x - 0.5) * (y - 0.75)
                points.append(CalibrationPoint(image: Point(x: x, y: y), pan: pan, tilt: 30 - 34 * y, rangeM: range))
            }
        }
        let coupledCalibration = Calibration(
            points: points,
            heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4.0),
                             HeightOffsetSample(rangeM: 6, deltaTiltDeg: 2.0)]
        )
        let aimer = try XCTUnwrap(Aimer(calibration: coupledCalibration))

        let x = 0.9
        let range = 4.5   // safely above split + blend/2, so this is a clean, full head shot
        let groundY = (8.0 - range) / 6.0
        let ground = Point(x: x, y: groundY)
        let head = Point(x: x, y: groundY - 0.06)

        let solution = aimer.solve(groundPoint: ground, headPoint: head)
        XCTAssertEqual(solution.target, .head)
        XCTAssertFalse(solution.isFlagged)

        let expectedPanAtHead = (x - 0.5) * 100 + 15 * (x - 0.5) * (head.y - 0.75)
        let expectedPanAtGround = (x - 0.5) * 100 + 15 * (x - 0.5) * (ground.y - 0.75)

        // The Aimer must have used the head point, not the ground point.
        XCTAssertEqual(solution.pan, expectedPanAtHead, accuracy: 0.1)
        XCTAssertGreaterThan(abs(expectedPanAtHead - expectedPanAtGround), 0.2,
                              "the coupling must be strong enough for this test to mean anything")
        XCTAssertGreaterThan(abs(solution.pan - expectedPanAtGround), 0.15,
                              "solving from the head point must give a measurably different pan than the ground point would")
    }
}
