import Foundation
import DwarfCore

public struct PixelSize: Equatable, Hashable, Sendable {
    public let width: Int
    public let height: Int

    public init(width: Int, height: Int) {
        self.width = width
        self.height = height
    }
}

public struct PixelPoint: Equatable, Hashable, Sendable {
    public let x: Int
    public let y: Int

    public init(x: Int, y: Int) {
        self.x = x
        self.y = y
    }
}

public struct PixelRect: Equatable, Hashable, Sendable {
    public let x: Int
    public let y: Int
    public let width: Int
    public let height: Int

    public init(x: Int, y: Int, width: Int, height: Int) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}

/// Which way is down, and where things are.
///
/// `DwarfCore` reads an animal's ground point as the bottom edge of its box, which is only
/// the ground if down in the image is down in the world. The camera does not know how the
/// phone was bolted into the gnome, so the mount is stated here as a number of quarter
/// turns clockwise applied to the camera buffer to stand the picture upright. A phone lying
/// on its side needs none, which is why that is the mount this project prefers: at 10 fps on
/// an A9, a rotation nobody needs is heat nobody wants.
public struct FrameGeometry: Equatable, Sendable {
    public let buffer: PixelSize
    /// 0, 1, 2 or 3. Values outside that range are taken modulo 4.
    public let quarterTurns: Int
    /// The buffer as `DwarfCore` sees it, after the turns.
    public let frame: PixelSize

    public init(buffer: PixelSize, quarterTurns: Int) {
        self.buffer = buffer
        let turns = ((quarterTurns % 4) + 4) % 4
        self.quarterTurns = turns
        self.frame = turns % 2 == 0
            ? buffer
            : PixelSize(width: buffer.height, height: buffer.width)
    }

    /// Feed these straight into `SchedulerConfig`, never a remembered constant: the crop
    /// rectangles it produces are fractions of exactly this frame, and the app is the only
    /// thing that knows how big the frame really is.
    public func apply(to config: inout SchedulerConfig) {
        config.frameWidthPixels = frame.width
        config.frameHeightPixels = frame.height
    }

    /// Where a pixel of the upright frame lives in the camera's buffer.
    public func bufferPoint(frameX: Int, frameY: Int) -> PixelPoint {
        switch quarterTurns {
        case 1:  return PixelPoint(x: frameY, y: buffer.height - 1 - frameX)
        case 2:  return PixelPoint(x: buffer.width - 1 - frameX, y: buffer.height - 1 - frameY)
        case 3:  return PixelPoint(x: buffer.width - 1 - frameY, y: frameX)
        default: return PixelPoint(x: frameX, y: frameY)
        }
    }

    /// A normalised rectangle in frame coordinates as whole pixels of that same frame,
    /// clamped to it. Clamping rather than refusing, because a crop that runs off the edge
    /// is still a useful crop of what is left.
    ///
    /// The width is rounded from the width, not derived by subtracting a rounded origin
    /// from a rounded far edge. That sounds like a distinction without a difference and is
    /// not: 640/1920 is one third, which has no exact binary representation, so
    /// `x * 1920` for an origin of 123 comes back as 122.99999999999999. Flooring that and
    /// ceiling the far edge turned a 640-pixel crop into a 641-pixel one at about one
    /// origin in twenty, and `Letterbox` then scaled the "square" by 0.9984 and padded it
    /// by half a pixel. Rounding each quantity from the number it actually represents
    /// keeps a crop the size the scheduler asked for.
    public func pixelRect(of rect: Rect) -> PixelRect {
        let width = Double(frame.width)
        let height = Double(frame.height)

        let x = Int(clamp((rect.x * width).rounded(), 0, width - 1))
        let y = Int(clamp((rect.y * height).rounded(), 0, height - 1))
        // At least one pixel, and never past the far edge: a rectangle that starts outside
        // the frame used to come back one pixel wider than the frame itself, which is an
        // out-of-bounds read for anything that trusts the docstring above.
        let w = Int(clamp((rect.width * width).rounded(), 1, width - Double(x)))
        let h = Int(clamp((rect.height * height).rounded(), 1, height - Double(y)))

        return PixelRect(x: x, y: y, width: w, height: h)
    }

    /// `pixelRect(of:)` for input that may not be trustworthy: a rectangle off a disk file
    /// or a web form. Returns nil rather than a clamped guess when the numbers are not
    /// usable at all.
    public func validPixelRect(of rect: Rect) -> PixelRect? {
        guard rect.x.isFinite, rect.y.isFinite, rect.width.isFinite, rect.height.isFinite,
              rect.width > 0, rect.height > 0 else { return nil }
        let pixels = pixelRect(of: rect)
        guard pixels.x < frame.width, pixels.y < frame.height else { return nil }
        return pixels
    }

    private func clamp(_ v: Double, _ low: Double, _ high: Double) -> Double {
        v.isFinite ? min(max(v, low), high) : low
    }
}

/// How a crop of the frame sits inside the model's square input.
///
/// The model wants a fixed square. Crops are not square — a sweep tile is half the frame,
/// taller than it is wide — so the crop is scaled to fit and the leftover is padded evenly
/// on the two short sides. Every box the model returns has to come back out through the
/// same arithmetic, and a sign error here puts the water a metre from the cat while every
/// test in `DwarfCore` still passes.
public struct Letterbox: Equatable, Sendable {
    /// Crop pixels to model pixels.
    public let scale: Double
    /// Padding on the left, in model pixels. Zero when the crop is wider than it is tall.
    public let offsetX: Double
    /// Padding on the top, in model pixels.
    public let offsetY: Double
    /// The model's input side, 640 unless M0 said otherwise.
    public let side: Int

    public init(crop: PixelRect, side: Int) {
        self.side = side
        let target = Double(side)
        let width = Double(max(crop.width, 1))
        let height = Double(max(crop.height, 1))
        let scale = min(target / width, target / height)
        self.scale = scale
        self.offsetX = (target - width * scale) / 2
        self.offsetY = (target - height * scale) / 2
    }

    /// A box the model returned, normalised to its square input, as a box in normalised
    /// frame coordinates.
    public func frameBox(fromModel box: Rect, crop: PixelRect, frame: PixelSize) -> Rect {
        let target = Double(side)
        let cropX = (box.x * target - offsetX) / scale
        let cropY = (box.y * target - offsetY) / scale
        return Rect(x: (Double(crop.x) + cropX) / Double(frame.width),
                    y: (Double(crop.y) + cropY) / Double(frame.height),
                    width: box.width * target / scale / Double(frame.width),
                    height: box.height * target / scale / Double(frame.height))
    }

    /// The inverse, which exists so the round trip can be tested and so a recorded frame
    /// can be re-cropped later for the dataset.
    public func modelBox(fromFrame box: Rect, crop: PixelRect, frame: PixelSize) -> Rect {
        let target = Double(side)
        let cropX = box.x * Double(frame.width) - Double(crop.x)
        let cropY = box.y * Double(frame.height) - Double(crop.y)
        return Rect(x: (cropX * scale + offsetX) / target,
                    y: (cropY * scale + offsetY) / target,
                    width: box.width * Double(frame.width) * scale / target,
                    height: box.height * Double(frame.height) * scale / target)
    }
}
