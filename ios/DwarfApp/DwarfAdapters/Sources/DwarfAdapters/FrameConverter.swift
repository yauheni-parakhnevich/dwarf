import Foundation
import CoreVideo
import Accelerate
import DwarfCore

/// Camera buffers in, the two things the pipeline actually wants out.
///
/// The capture session is configured for `420YpCbCr8BiPlanarFullRange`, which is the
/// camera's native format, so no conversion happens at capture time and plane 0 is already
/// the grayscale image motion detection needs — motion detection costs no colour work at
/// all.
///
/// Colour is produced only when a crop is actually going to the model, which is a few times
/// a cycle rather than on every frame. The conversion itself is whole-frame: vImage's
/// planar YCbCr path wants both planes together, and chroma is subsampled, so converting an
/// arbitrary sub-rectangle means handling odd-aligned edges for a saving that measured
/// under a millisecond. The 8 MB working buffer is allocated once and reused rather than
/// per call, which was the part actually worth fixing.
public final class FrameConverter {
    /// What the letterbox is filled with. 114 is the value Ultralytics pads with, so the
    /// model has seen this exact grey around its training images.
    public static let padding: UInt8 = 114

    public let geometry: FrameGeometry
    /// Size of the motion-detection frame, in frame orientation.
    public let graySize: PixelSize

    private let grayLongSide: Int
    /// Full-frame ARGB working buffer, allocated once and reused. Owned here, so no caller
    /// frees what `bgra(from:)` returns.
    private var argbScratch: vImage_Buffer?

    deinit {
        if let scratch = argbScratch { free(scratch.data) }
    }

    public init(geometry: FrameGeometry, grayLongSide: Int = 480) {
        self.geometry = geometry
        self.grayLongSide = grayLongSide

        // The long side is the budget, so portrait costs the same as landscape rather than
        // scaling with whichever way the phone was bolted in.
        let frame = geometry.frame
        let long = max(frame.width, frame.height)
        let short = min(frame.width, frame.height)
        let scaledShort = max(1, Int((Double(grayLongSide) * Double(short) / Double(long)).rounded()))
        self.graySize = frame.width >= frame.height
            ? PixelSize(width: grayLongSide, height: scaledShort)
            : PixelSize(width: scaledShort, height: grayLongSide)
    }

    // MARK: motion

    /// The luma plane, scaled down and stood upright.
    public func gray(from pixelBuffer: CVPixelBuffer) -> GrayFrame? {
        guard CVPixelBufferGetWidth(pixelBuffer) == geometry.buffer.width,
              CVPixelBufferGetHeight(pixelBuffer) == geometry.buffer.height else { return nil }
        guard CVPixelBufferGetPlaneCount(pixelBuffer) >= 1 else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else { return nil }

        var source = vImage_Buffer(data: base,
                                   height: vImagePixelCount(geometry.buffer.height),
                                   width: vImagePixelCount(geometry.buffer.width),
                                   rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0))

        // Scale in buffer orientation, then turn: scaling first means the rotation moves a
        // few hundred kilobytes rather than two megabytes.
        let scaledWidth = geometry.quarterTurns % 2 == 0 ? graySize.width : graySize.height
        let scaledHeight = geometry.quarterTurns % 2 == 0 ? graySize.height : graySize.width

        var scaled = [UInt8](repeating: 0, count: scaledWidth * scaledHeight)
        var scaleError = kvImageNoError
        scaled.withUnsafeMutableBytes { raw in
            var destination = vImage_Buffer(data: raw.baseAddress,
                                            height: vImagePixelCount(scaledHeight),
                                            width: vImagePixelCount(scaledWidth),
                                            rowBytes: scaledWidth)
            scaleError = vImageScale_Planar8(&source, &destination, nil, vImage_Flags(kvImageNoFlags))
        }
        guard scaleError == kvImageNoError else { return nil }

        guard let upright = rotated(planar: scaled, width: scaledWidth, height: scaledHeight) else {
            return nil
        }
        return GrayFrame(validating: graySize.width, height: graySize.height, pixels: upright)
    }

    private func rotated(planar pixels: [UInt8], width: Int, height: Int) -> [UInt8]? {
        guard geometry.quarterTurns != 0 else { return pixels }

        let constant: UInt8
        switch geometry.quarterTurns {
        case 1: constant = UInt8(kRotate90DegreesClockwise)
        case 2: constant = UInt8(kRotate180DegreesClockwise)
        default: constant = UInt8(kRotate270DegreesClockwise)
        }

        // A quarter or three-quarter turn transposes; a half turn does not. Swapping
        // unconditionally gave vImage a destination whose declared row stride did not match
        // the rows it was writing, which it accepts without complaint and which scrambles
        // the image rather than rotating it.
        let turnedWidth = geometry.quarterTurns % 2 == 0 ? width : height
        let turnedHeight = geometry.quarterTurns % 2 == 0 ? height : width

        var output = [UInt8](repeating: 0, count: pixels.count)
        var source = pixels
        var error = kvImageNoError
        source.withUnsafeMutableBytes { sourceRaw in
            var input = vImage_Buffer(data: sourceRaw.baseAddress,
                                      height: vImagePixelCount(height),
                                      width: vImagePixelCount(width),
                                      rowBytes: width)
            output.withUnsafeMutableBytes { outputRaw in
                var destination = vImage_Buffer(data: outputRaw.baseAddress,
                                                height: vImagePixelCount(turnedHeight),
                                                width: vImagePixelCount(turnedWidth),
                                                rowBytes: turnedWidth)
                error = vImageRotate90_Planar8(&input, &destination, constant, 0,
                                               vImage_Flags(kvImageNoFlags))
            }
        }
        return error == kvImageNoError ? output : nil
    }

    // MARK: detection

    /// One crop of the frame, in colour, letterboxed into the square the model wants.
    ///
    /// `cropInFrame` is in upright frame pixels — the same coordinates `FrameGeometry`
    /// produced it in — and is mapped back into the camera's buffer here.
    public func modelInput(from pixelBuffer: CVPixelBuffer, cropInFrame crop: PixelRect,
                           side: Int) -> CVPixelBuffer? {
        guard crop.width > 0, crop.height > 0, side > 0 else { return nil }
        guard crop.x >= 0, crop.y >= 0,
              crop.x + crop.width <= geometry.frame.width,
              crop.y + crop.height <= geometry.frame.height else { return nil }
        guard CVPixelBufferGetWidth(pixelBuffer) == geometry.buffer.width,
              CVPixelBufferGetHeight(pixelBuffer) == geometry.buffer.height else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }

        guard let colour = bgra(from: pixelBuffer) else { return nil }

        // The crop's two opposite corners, carried into buffer space. A rotation keeps a
        // rectangle a rectangle; it just may arrive with its corners swapped.
        let a = geometry.bufferPoint(frameX: crop.x, frameY: crop.y)
        let b = geometry.bufferPoint(frameX: crop.x + crop.width - 1,
                                     frameY: crop.y + crop.height - 1)
        let originX = min(a.x, b.x)
        let originY = min(a.y, b.y)
        let regionWidth = abs(b.x - a.x) + 1
        let regionHeight = abs(b.y - a.y) + 1

        var region = vImage_Buffer(
            data: colour.data.advanced(by: originY * colour.rowBytes + originX * 4),
            height: vImagePixelCount(regionHeight),
            width: vImagePixelCount(regionWidth),
            rowBytes: colour.rowBytes)

        guard var upright = rotatedColour(&region, width: regionWidth, height: regionHeight) else {
            return nil
        }
        defer { if geometry.quarterTurns != 0 { free(upright.data) } }

        return letterboxed(&upright, side: side)
    }

    private func bgra(from pixelBuffer: CVPixelBuffer) -> vImage_Buffer? {
        let width = geometry.buffer.width
        let height = geometry.buffer.height
        guard let yBase = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0),
              let uvBase = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1) else { return nil }

        var luma = vImage_Buffer(data: yBase, height: vImagePixelCount(height),
                                 width: vImagePixelCount(width),
                                 rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0))
        var chroma = vImage_Buffer(data: uvBase, height: vImagePixelCount(height / 2),
                                   width: vImagePixelCount(width / 2),
                                   rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1))

        // One buffer, reused. A full-frame ARGB allocation is about 8 MB, and mallocing
        // and freeing that on every crop request is page churn a 2 GB phone does not need.
        // Not thread-safe, deliberately: both entry points are called from the capture
        // queue and nowhere else.
        var destination: vImage_Buffer
        if let existing = argbScratch {
            destination = existing
        } else {
            var fresh = vImage_Buffer()
            guard vImageBuffer_Init(&fresh, vImagePixelCount(height), vImagePixelCount(width),
                                    32, vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }
            argbScratch = fresh
            destination = fresh
        }

        var info = vImage_YpCbCrToARGB()
        var pixelRange = vImage_YpCbCrPixelRange(Yp_bias: 0, CbCr_bias: 128, YpRangeMax: 255,
                                                 CbCrRangeMax: 255, YpMax: 255, YpMin: 0,
                                                 CbCrMax: 255, CbCrMin: 0)
        guard vImageConvert_YpCbCrToARGB_GenerateConversion(
                kvImage_YpCbCrToARGBMatrix_ITU_R_601_4, &pixelRange, &info,
                kvImage420Yp8_CbCr8, kvImageARGB8888,
                vImage_Flags(kvImageNoFlags)) == kvImageNoError else {
            return nil
        }

        // The map puts the channels in BGRA order, which is what CoreML's image input and
        // every debugging tool expect.
        let map: [UInt8] = [3, 2, 1, 0]
        guard vImageConvert_420Yp8_CbCr8ToARGB8888(&luma, &chroma, &destination, &info, map, 255,
                                                   vImage_Flags(kvImageNoFlags)) == kvImageNoError else {
            return nil
        }
        return destination
    }

    private func rotatedColour(_ region: inout vImage_Buffer, width: Int,
                               height: Int) -> vImage_Buffer? {
        guard geometry.quarterTurns != 0 else { return region }

        let constant: UInt8
        switch geometry.quarterTurns {
        case 1: constant = UInt8(kRotate90DegreesClockwise)
        case 2: constant = UInt8(kRotate180DegreesClockwise)
        default: constant = UInt8(kRotate270DegreesClockwise)
        }

        let turnedWidth = geometry.quarterTurns % 2 == 0 ? width : height
        let turnedHeight = geometry.quarterTurns % 2 == 0 ? height : width

        var destination = vImage_Buffer()
        guard vImageBuffer_Init(&destination, vImagePixelCount(turnedHeight),
                                vImagePixelCount(turnedWidth), 32,
                                vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }

        var background: [UInt8] = [FrameConverter.padding, FrameConverter.padding,
                                   FrameConverter.padding, 255]
        let error = vImageRotate90_ARGB8888(&region, &destination, constant, &background,
                                            vImage_Flags(kvImageNoFlags))
        guard error == kvImageNoError else {
            free(destination.data)
            return nil
        }
        return destination
    }

    private func letterboxed(_ region: inout vImage_Buffer, side: Int) -> CVPixelBuffer? {
        let box = Letterbox(crop: PixelRect(x: 0, y: 0, width: Int(region.width),
                                            height: Int(region.height)),
                            side: side)
        let innerWidth = max(1, Int((Double(region.width) * box.scale).rounded()))
        let innerHeight = max(1, Int((Double(region.height) * box.scale).rounded()))

        var output: CVPixelBuffer?
        let attributes: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary]
        guard CVPixelBufferCreate(kCFAllocatorDefault, side, side, kCVPixelFormatType_32BGRA,
                                  attributes as CFDictionary, &output) == kCVReturnSuccess,
              let output else { return nil }

        CVPixelBufferLockBaseAddress(output, [])
        defer { CVPixelBufferUnlockBaseAddress(output, []) }
        guard let base = CVPixelBufferGetBaseAddress(output) else { return nil }
        let rowBytes = CVPixelBufferGetBytesPerRow(output)

        // Fill first, so whatever the scale does not cover is the padding value the model
        // was trained against rather than uninitialised memory.
        for row in 0..<side {
            memset(base.advanced(by: row * rowBytes), Int32(FrameConverter.padding), side * 4)
        }

        let insetX = Int(box.offsetX.rounded())
        let insetY = Int(box.offsetY.rounded())
        var destination = vImage_Buffer(
            data: base.advanced(by: insetY * rowBytes + insetX * 4),
            height: vImagePixelCount(innerHeight),
            width: vImagePixelCount(innerWidth),
            rowBytes: rowBytes)

        guard vImageScale_ARGB8888(&region, &destination, nil,
                                   vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }
        return output
    }
}
