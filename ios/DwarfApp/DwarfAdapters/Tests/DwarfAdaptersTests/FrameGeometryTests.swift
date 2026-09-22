import XCTest
import DwarfCore
@testable import DwarfAdapters

final class FrameGeometryTests: XCTestCase {
    private let buffer = PixelSize(width: 1920, height: 1080)

    func testALandscapeMountNeedsNoRotation() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        XCTAssertEqual(geometry.frame, PixelSize(width: 1920, height: 1080))
        XCTAssertEqual(geometry.bufferPoint(frameX: 100, frameY: 50), PixelPoint(x: 100, y: 50))
    }

    func testAQuarterTurnSwapsTheFrameDimensions() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 1)
        XCTAssertEqual(geometry.frame, PixelSize(width: 1080, height: 1920))
    }

    func testEveryRotationMapsCornersToCorners() {
        // The cheapest possible check that a rotation is a rotation and not a fold: the
        // four frame corners must land on the four buffer corners, once each.
        for turns in 0..<4 {
            let geometry = FrameGeometry(buffer: buffer, quarterTurns: turns)
            let w = geometry.frame.width - 1
            let h = geometry.frame.height - 1
            let mapped = Set([
                geometry.bufferPoint(frameX: 0, frameY: 0),
                geometry.bufferPoint(frameX: w, frameY: 0),
                geometry.bufferPoint(frameX: 0, frameY: h),
                geometry.bufferPoint(frameX: w, frameY: h)
            ])
            let corners: Set<PixelPoint> = [
                PixelPoint(x: 0, y: 0),
                PixelPoint(x: 1919, y: 0),
                PixelPoint(x: 0, y: 1079),
                PixelPoint(x: 1919, y: 1079)
            ]
            XCTAssertEqual(mapped, corners, "quarterTurns \(turns)")
        }
    }

    func testACropRequestBecomesAPixelRectangle() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let request = CropRequest(rect: Rect(x: 0.25, y: 0.5, width: 0.25, height: 0.25),
                                  kind: .motion)
        let rect = geometry.pixelRect(of: request.rect)

        XCTAssertEqual(rect.x, 480)
        XCTAssertEqual(rect.y, 540)
        XCTAssertEqual(rect.width, 480)
        XCTAssertEqual(rect.height, 270)
    }

    func testACropRectangleIsClampedIntoTheFrame() {
        // Scheduler clamps its own rects, but a mask editor or a settings file can hand
        // over something that starts inside the frame and runs off the edge. Extracting
        // pixels from outside the buffer is a crash, not a bad crop.
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let rect = geometry.pixelRect(of: Rect(x: 0.9, y: 0.9, width: 0.5, height: 0.5))

        XCTAssertEqual(rect.x + rect.width, 1920)
        XCTAssertEqual(rect.y + rect.height, 1080)
        XCTAssertGreaterThan(rect.width, 0)
    }

    func testANonFiniteCropRectangleIsRefused() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        XCTAssertNil(geometry.validPixelRect(of: Rect(x: .nan, y: 0, width: 0.1, height: 0.1)))
        XCTAssertNil(geometry.validPixelRect(of: Rect(x: 0, y: 0, width: 0, height: 0.1)))
    }

    func testALetterboxedBoxComesBackToWhereItStarted() {
        // The round trip that matters: a box drawn in frame coordinates, projected into
        // the model's padded square, and read back out must land where it began. Every
        // sign error in the letterbox arithmetic shows up here.
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let crop = geometry.pixelRect(of: Rect(x: 0.1, y: 0.4, width: 0.5, height: 0.3))
        let letterbox = Letterbox(crop: crop, side: 640)

        let original = Rect(x: 0.2, y: 0.45, width: 0.08, height: 0.06)
        let inModel = letterbox.modelBox(fromFrame: original, crop: crop, frame: geometry.frame)
        let returned = letterbox.frameBox(fromModel: inModel, crop: crop, frame: geometry.frame)

        XCTAssertEqual(returned.x, original.x, accuracy: 1e-9)
        XCTAssertEqual(returned.y, original.y, accuracy: 1e-9)
        XCTAssertEqual(returned.width, original.width, accuracy: 1e-9)
        XCTAssertEqual(returned.height, original.height, accuracy: 1e-9)
    }

    func testTheLetterboxPadsTheShorterSide() {
        // A 960×1080 sweep tile is taller than it is wide, so it is scaled to fit the
        // height and padded left and right.
        let letterbox = Letterbox(crop: PixelRect(x: 0, y: 0, width: 960, height: 1080), side: 640)

        XCTAssertEqual(letterbox.scale, 640.0 / 1080.0, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetY, 0, accuracy: 1e-12)
        XCTAssertGreaterThan(letterbox.offsetX, 0)
        XCTAssertEqual(letterbox.offsetX * 2 + 960 * letterbox.scale, 640, accuracy: 1e-9)
    }

    func testASquareCropIsNotPaddedAtAll() {
        let letterbox = Letterbox(crop: PixelRect(x: 0, y: 0, width: 640, height: 640), side: 640)
        XCTAssertEqual(letterbox.scale, 1, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetX, 0, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetY, 0, accuracy: 1e-12)
    }
}
