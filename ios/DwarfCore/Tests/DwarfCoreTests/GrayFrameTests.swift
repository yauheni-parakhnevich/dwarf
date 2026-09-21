import XCTest
@testable import DwarfCore

final class GrayFrameTests: XCTestCase {
    func testPixelAccess() {
        let frame = GrayFrame(width: 3, height: 2, pixels: [0, 1, 2, 3, 4, 5])
        XCTAssertEqual(frame.luma(x: 0, y: 0), 0)
        XCTAssertEqual(frame.luma(x: 2, y: 0), 2)
        XCTAssertEqual(frame.luma(x: 0, y: 1), 3)
        XCTAssertEqual(frame.luma(x: 2, y: 1), 5)
    }

    func testMeanLuma() {
        XCTAssertEqual(GrayFrame(width: 2, height: 2, pixels: [0, 100, 100, 200]).meanLuma,
                       100, accuracy: 1e-9)
    }

    func testMeanLumaOfEmptyFrameIsZero() {
        XCTAssertEqual(GrayFrame(width: 0, height: 0, pixels: []).meanLuma, 0, accuracy: 1e-9)
    }

    func testMismatchedPixelCountIsRejected() {
        XCTAssertNil(GrayFrame(validating: 2, height: 2, pixels: [1, 2, 3]))
        XCTAssertNotNil(GrayFrame(validating: 2, height: 2, pixels: [1, 2, 3, 4]))
    }

    /// Every valid coordinate of a small frame, including all four corners, must return
    /// its expected value without tripping the `precondition` in `luma(x:y:)`.
    ///
    /// The case the precondition actually exists for — a negative `x` paired with a
    /// positive `y` computing a flat index that still lands inside the buffer — traps by
    /// design, and XCTest cannot catch an in-process trap, so it cannot be exercised as a
    /// test here.
    func testLumaAcceptsEveryValidCoordinate() {
        let frame = GrayFrame(width: 3, height: 2, pixels: [10, 11, 12, 13, 14, 15])
        var expected: UInt8 = 10
        for y in 0..<frame.height {
            for x in 0..<frame.width {
                XCTAssertEqual(frame.luma(x: x, y: y), expected)
                expected += 1
            }
        }
    }

    func testValidatingInitializerAlwaysProducesConsistentFrame() {
        guard let frame = GrayFrame(validating: 3, height: 2, pixels: [10, 20, 30, 40, 50, 60]) else {
            return XCTFail("expected a valid frame")
        }
        XCTAssertEqual(frame.pixels.count, frame.width * frame.height)
        let handComputedMean = (10.0 + 20.0 + 30.0 + 40.0 + 50.0 + 60.0) / 6.0
        XCTAssertEqual(frame.meanLuma, handComputedMean, accuracy: 1e-9)
    }
}
