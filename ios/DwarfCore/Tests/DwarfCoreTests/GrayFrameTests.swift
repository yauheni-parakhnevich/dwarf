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
}
