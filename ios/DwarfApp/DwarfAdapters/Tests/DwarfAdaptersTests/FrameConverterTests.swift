import XCTest
import CoreVideo
import DwarfCore
@testable import DwarfAdapters

final class FrameConverterTests: XCTestCase {
    /// A 420f buffer with a flat luma value, and optionally one brighter rectangle, so a
    /// test can tell where a region ended up after scaling and rotation.
    private func makeBuffer(width: Int = 1920, height: Int = 1080,
                            luma: UInt8 = 40,
                            bright: (x: Int, y: Int, w: Int, h: Int)? = nil,
                            brightLuma: UInt8 = 240) -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        let attributes: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary]
        let status = CVPixelBufferCreate(kCFAllocatorDefault, width, height,
                                         kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
                                         attributes as CFDictionary, &buffer)
        guard status == kCVReturnSuccess, let buffer else {
            fatalError("could not create a test pixel buffer: \(status)")
        }

        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }

        let y = CVPixelBufferGetBaseAddressOfPlane(buffer, 0)!.assumingMemoryBound(to: UInt8.self)
        let yStride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
        for row in 0..<height {
            memset(y.advanced(by: row * yStride), Int32(luma), width)
        }
        if let bright {
            for row in bright.y..<(bright.y + bright.h) {
                memset(y.advanced(by: row * yStride + bright.x), Int32(brightLuma), bright.w)
            }
        }

        // Neutral chroma, so the colour conversion has something defined to do.
        let uv = CVPixelBufferGetBaseAddressOfPlane(buffer, 1)!.assumingMemoryBound(to: UInt8.self)
        let uvStride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 1)
        for row in 0..<(height / 2) {
            memset(uv.advanced(by: row * uvStride), 128, width)
        }
        return buffer
    }

    func testTheGrayFrameKeepsTheFramesAspectRatio() throws {
        // DwarfCore's contract: the small frame and the full frame must describe the same
        // field of view, because blob rectangles from one are used to cut crops from the
        // other.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: makeBuffer()))

        XCTAssertEqual(frame.width, 480)
        XCTAssertEqual(frame.height, 270)
        XCTAssertEqual(Double(frame.width) / Double(frame.height), 1920.0 / 1080.0, accuracy: 0.01)
    }

    func testTheGrayFrameCarriesTheLuma() throws {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: makeBuffer(luma: 90)))
        XCTAssertEqual(frame.meanLuma, 90, accuracy: 2)
    }

    func testAQuarterTurnMovesTheBrightCornerWhereExpected() throws {
        // A bright patch in the buffer's top-left must appear in the frame's TOP-RIGHT
        // after one clockwise turn: turning a picture clockwise swings its left edge up to
        // become the top, carrying the top-left corner round to the right. This is the test
        // that catches a rotation applied the wrong way round, which otherwise only shows
        // up as the gnome aiming at the sky.
        let buffer = makeBuffer(bright: (x: 0, y: 0, w: 400, h: 200))
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 1),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: buffer))

        XCTAssertEqual(frame.width, 270)
        XCTAssertEqual(frame.height, 480)
        XCTAssertGreaterThan(frame.luma(x: frame.width - 10, y: 20), 200)
        XCTAssertLessThan(frame.luma(x: 10, y: 20), 100)
    }

    func testTheGrayLongSideIsHonouredInBothMounts() throws {
        // Portrait must not cost three times the motion-detection work just because the
        // frame got taller. The long side is the budget, whichever way it points.
        let landscape = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let portrait = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                             quarterTurns: 1),
                                      grayLongSide: 480)

        XCTAssertEqual(max(landscape.graySize.width, landscape.graySize.height), 480)
        XCTAssertEqual(max(portrait.graySize.width, portrait.graySize.height), 480)
        XCTAssertEqual(landscape.graySize.width * landscape.graySize.height,
                       portrait.graySize.width * portrait.graySize.height)
    }

    func testTheModelInputIsASquareOfTheRequestedSide() throws {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        // Full frame height: y + height must stay inside the frame, or modelInput's own
        // bounds guard refuses the crop and this test measures nothing.
        let crop = PixelRect(x: 100, y: 0, width: 960, height: 1080)
        let input = try XCTUnwrap(converter.modelInput(from: makeBuffer(), cropInFrame: crop, side: 640))

        XCTAssertEqual(CVPixelBufferGetWidth(input), 640)
        XCTAssertEqual(CVPixelBufferGetHeight(input), 640)
        XCTAssertEqual(CVPixelBufferGetPixelFormatType(input), kCVPixelFormatType_32BGRA)
    }

    func testTheModelInputPadsRatherThanStretches() throws {
        // A tall crop letterboxed into a square must have padding down its sides, and the
        // padding must be the value the model was trained to ignore rather than black.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let crop = PixelRect(x: 0, y: 0, width: 540, height: 1080)
        let input = try XCTUnwrap(converter.modelInput(from: makeBuffer(luma: 200),
                                                       cropInFrame: crop, side: 640))

        CVPixelBufferLockBaseAddress(input, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(input, .readOnly) }
        let base = CVPixelBufferGetBaseAddress(input)!.assumingMemoryBound(to: UInt8.self)
        let stride = CVPixelBufferGetBytesPerRow(input)

        // Far left column: padding. Centre: image.
        let leftBlue = base[320 * stride + 0]
        let centreBlue = base[320 * stride + 320 * 4]
        XCTAssertEqual(leftBlue, FrameConverter.padding)
        XCTAssertNotEqual(centreBlue, FrameConverter.padding)
    }

    func testAnEmptyOrImpossibleCropIsRefusedRatherThanCrashing() {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let buffer = makeBuffer()
        XCTAssertNil(converter.modelInput(from: buffer,
                                          cropInFrame: PixelRect(x: 0, y: 0, width: 0, height: 100),
                                          side: 640))
        XCTAssertNil(converter.modelInput(from: buffer,
                                          cropInFrame: PixelRect(x: 5000, y: 0, width: 100, height: 100),
                                          side: 640))
    }

    func testAWronglySizedBufferIsRefused() {
        // The geometry was built for 1920×1080. If the capture session ever hands over
        // something else, every crop rectangle computed from it is wrong, and saying so is
        // better than quietly cropping the wrong part of the garden.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        XCTAssertNil(converter.gray(from: makeBuffer(width: 1280, height: 720)))
    }

    func testEveryRotationKeepsTheImage() throws {
        // A 180 degree turn does not transpose, and building its destination buffer as if
        // it did wrote rows at the wrong stride: vImage reported success and the picture
        // came out scrambled, with the bright patch simply gone. Motion detection on an
        // upside-down mount would have quietly seen nothing at all.
        for turns in 0..<4 {
            let converter = FrameConverter(
                geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                        quarterTurns: turns),
                grayLongSide: 480)
            let frame = try XCTUnwrap(converter.gray(from: makeBuffer(bright: (x: 0, y: 0, w: 400, h: 200))),
                                      "quarterTurns \(turns)")

            var brightest: UInt8 = 0
            for y in 0..<frame.height {
                for x in 0..<frame.width {
                    brightest = max(brightest, frame.luma(x: x, y: y))
                }
            }
            XCTAssertGreaterThan(brightest, 200, "the bright patch vanished at quarterTurns \(turns)")
        }
    }
}
