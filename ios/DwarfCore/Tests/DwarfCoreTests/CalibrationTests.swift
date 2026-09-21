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
}
