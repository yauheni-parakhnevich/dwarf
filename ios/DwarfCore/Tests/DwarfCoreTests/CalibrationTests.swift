import XCTest
@testable import DwarfCore

final class CalibrationTests: XCTestCase {
    private var sample: Calibration {
        Calibration(
            points: [
                CalibrationPoint(image: Point(x: 0.3, y: 0.8), pan: -12, tilt: -5, rangeM: 2.5),
                CalibrationPoint(image: Point(x: 0.5, y: 0.7), pan: 0, tilt: 2, rangeM: 4.0)
            ],
            heightOffsets: [
                HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 3.2),
                HeightOffsetSample(rangeM: 6.0, deltaTiltDeg: 2.1)
            ]
        )
    }

    func testRoundTripsThroughJSON() throws {
        let data = try JSONEncoder().encode(sample)
        XCTAssertEqual(try JSONDecoder().decode(Calibration.self, from: data), sample)
    }

    func testEmptyCalibrationIsEmpty() {
        XCTAssertTrue(Calibration.empty.points.isEmpty)
        XCTAssertTrue(Calibration.empty.heightOffsets.isEmpty)
    }

    func testHeightOffsetInterpolatesBetweenSamples() throws {
        XCTAssertEqual(try XCTUnwrap(sample.heightOffset(atRange: 5.0)), 2.65, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(sample.heightOffset(atRange: 4.5)), 2.925, accuracy: 1e-9)
    }

    func testHeightOffsetClampsOutsideTheCalibratedSpan() throws {
        XCTAssertEqual(try XCTUnwrap(sample.heightOffset(atRange: 2.0)), 3.2, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(sample.heightOffset(atRange: 9.0)), 2.1, accuracy: 1e-9)
    }

    func testHeightOffsetIsNilWithoutSamples() {
        XCTAssertNil(Calibration.empty.heightOffset(atRange: 5))
    }

    func testASingleHeightSampleAppliesEverywhere() throws {
        let one = Calibration(points: [], heightOffsets: [HeightOffsetSample(rangeM: 5, deltaTiltDeg: 2.7)])
        XCTAssertEqual(try XCTUnwrap(one.heightOffset(atRange: 2)), 2.7, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(one.heightOffset(atRange: 8)), 2.7, accuracy: 1e-9)
    }

    /// Two shots at the same range, with different readings, are one measurement averaged —
    /// not two points on a curve. Without averaging, interpolation would step at range 4
    /// (measured before this fix: 3.05 just below, then a discontinuous drop to 1.05 just
    /// above). With averaging the samples collapse to (2, 4), (4, 3), (6, 7), and the curve
    /// passes smoothly through range 4 at the average, 3.0.
    func testDuplicateRangesAverageInsteadOfStepping() throws {
        let calibration = Calibration(heightOffsets: [
            HeightOffsetSample(rangeM: 2.0, deltaTiltDeg: 4.0),
            HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 5.0),
            HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 1.0),
            HeightOffsetSample(rangeM: 6.0, deltaTiltDeg: 7.0)
        ])
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 3.9)), 3.05, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 4.0)), 3.0, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 4.1)), 3.2, accuracy: 1e-9)
    }

    /// The same averaging applies when the duplicate sits at the clamped low end: the clamp
    /// must return the average of both readings, not whichever happened to be added first.
    func testDuplicateAtTheClampedLowEndReturnsTheAverage() throws {
        let calibration = Calibration(heightOffsets: [
            HeightOffsetSample(rangeM: 2.0, deltaTiltDeg: 5.0),
            HeightOffsetSample(rangeM: 2.0, deltaTiltDeg: 9.0),
            HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 3.0)
        ])
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 1.0)), 7.0, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 2.0)), 7.0, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 3.0)), 5.0, accuracy: 1e-9)
    }

    /// The owner adds samples in whatever order they walk the lawn: insertion order, including
    /// where the duplicates land in that order, must not change the averaged result.
    func testUnsortedDuplicatesStillAverageCorrectly() throws {
        let calibration = Calibration(heightOffsets: [
            HeightOffsetSample(rangeM: 6.0, deltaTiltDeg: 7.0),
            HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 1.0),
            HeightOffsetSample(rangeM: 2.0, deltaTiltDeg: 4.0),
            HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 5.0)
        ])
        XCTAssertEqual(try XCTUnwrap(calibration.heightOffset(atRange: 4.0)), 3.0, accuracy: 1e-9)
    }
}
