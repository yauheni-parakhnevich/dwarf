import XCTest
@testable import DwarfCore

final class MotionDetectorTests: XCTestCase {
    /// A frame of uniform grey with a brighter filled square at the given top-left.
    private func frame(width: Int = 40, height: Int = 30,
                       squareX: Int? = nil, squareY: Int = 0, squareSize: Int = 6) -> GrayFrame {
        var pixels = [UInt8](repeating: 100, count: width * height)
        if let sx = squareX {
            for y in squareY..<(squareY + squareSize) {
                for x in sx..<(sx + squareSize) {
                    pixels[y * width + x] = 200
                }
            }
        }
        return GrayFrame(width: width, height: height, pixels: pixels)
    }

    func testFirstFrameProducesNoBlobs() {
        let detector = MotionDetector()
        XCTAssertTrue(detector.process(frame()).isEmpty)
    }

    func testStaticSceneProducesNoBlobs() {
        let detector = MotionDetector()
        _ = detector.process(frame())
        XCTAssertTrue(detector.process(frame()).isEmpty)
        XCTAssertTrue(detector.process(frame()).isEmpty)
    }

    func testMovingSquareIsFound() {
        var config = MotionConfig()
        config.minBlobArea = 4
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        let blobs = detector.process(frame(squareX: 10, squareY: 8))
        XCTAssertEqual(blobs.count, 1)

        let box = blobs[0].boundingBox
        // The square spans x 10..<16 of 40 and y 8..<14 of 30, plus one pixel of dilation.
        XCTAssertEqual(box.x, 9.0 / 40.0, accuracy: 0.03)
        XCTAssertEqual(box.y, 7.0 / 30.0, accuracy: 0.03)
        XCTAssertGreaterThan(box.width, 0.1)
        XCTAssertGreaterThan(box.height, 0.15)
    }

    func testTwoSeparateSquaresBecomeTwoBlobs() {
        var config = MotionConfig()
        config.minBlobArea = 4
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        var pixels = [UInt8](repeating: 100, count: 40 * 30)
        for y in 4..<10 { for x in 4..<10 { pixels[y * 40 + x] = 200 } }
        for y in 18..<24 { for x in 28..<34 { pixels[y * 40 + x] = 200 } }
        let blobs = detector.process(GrayFrame(width: 40, height: 30, pixels: pixels))

        XCTAssertEqual(blobs.count, 2)
    }

    func testBlobsSmallerThanTheMinimumAreDropped() {
        var config = MotionConfig()
        config.minBlobArea = 200
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())
        XCTAssertTrue(detector.process(frame(squareX: 10, squareY: 8)).isEmpty)
    }

    func testBackgroundAbsorbsAStoppedObject() {
        var config = MotionConfig()
        config.minBlobArea = 4
        config.backgroundAlpha = 0.5   // absorb fast, so the test stays short
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        let moved = frame(squareX: 10, squareY: 8)
        XCTAssertEqual(detector.process(moved).count, 1)
        for _ in 0..<12 { _ = detector.process(moved) }

        // This is exactly why the sweep tiles in the Scheduler exist: a cat that sits
        // still disappears from motion detection within seconds.
        XCTAssertTrue(detector.process(moved).isEmpty)
    }

    func testResetForgetsTheBackground() {
        let detector = MotionDetector()
        _ = detector.process(frame())
        detector.reset()
        XCTAssertTrue(detector.process(frame(squareX: 10, squareY: 8)).isEmpty,
                      "after reset the next frame is the new background, so nothing moves")
    }
}
