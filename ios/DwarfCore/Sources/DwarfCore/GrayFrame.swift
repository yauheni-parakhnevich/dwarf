import Foundation

/// One downscaled grayscale frame, row-major, 8 bits per pixel.
///
/// The iOS layer produces these at roughly 480×270 — small enough that background
/// subtraction over every pixel costs nothing, large enough that a cat at 6 m is still
/// several pixels across.
public struct GrayFrame: Equatable, Sendable {
    public let width: Int
    public let height: Int
    public let pixels: [UInt8]

    /// Trusting initialiser for callers that already know the buffer is the right size.
    ///
    /// The `assert` is debug-only by design: this initialiser exists so hot internal
    /// paths can skip the check `init(validating:)` does, so release builds pay nothing
    /// for it. Anything that cannot already guarantee the buffer size should use
    /// `init(validating:)` instead.
    public init(width: Int, height: Int, pixels: [UInt8]) {
        assert(
            pixels.count == width * height,
            "GrayFrame buffer size mismatch: \(width)x\(height) expects \(width * height) " +
            "pixels but got \(pixels.count)"
        )
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    /// Checking initialiser for anything crossing a boundary, such as a camera callback.
    public init?(validating width: Int, height: Int, pixels: [UInt8]) {
        guard width >= 0, height >= 0, pixels.count == width * height else { return nil }
        self.init(width: width, height: height, pixels: pixels)
    }

    /// Reads one pixel. Traps outside the frame — including a negative `x` paired with a
    /// positive `y`, which would otherwise compute a flat index that still lands inside
    /// the buffer and silently returns a pixel from the wrong row. A loud crash beats a
    /// quietly wrong frame diff.
    ///
    /// Not the hot path: the motion detector scans every pixel by iterating
    /// `pixels.indices` directly, so this check does not run once per pixel per frame.
    /// Do not remove it on the assumption that it does.
    public func luma(x: Int, y: Int) -> UInt8 {
        precondition(
            x >= 0 && x < width && y >= 0 && y < height,
            "GrayFrame.luma(x:y:) out of range: (x: \(x), y: \(y)) not within " +
            "0..<\(width) x 0..<\(height)"
        )
        return pixels[y * width + x]
    }

    /// Average brightness, used to pause detection once the yard goes dark.
    public var meanLuma: Double {
        guard !pixels.isEmpty else { return 0 }
        var total = 0
        for p in pixels { total += Int(p) }
        return Double(total) / Double(pixels.count)
    }
}
