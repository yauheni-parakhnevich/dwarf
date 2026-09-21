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
    public init(width: Int, height: Int, pixels: [UInt8]) {
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    /// Checking initialiser for anything crossing a boundary, such as a camera callback.
    public init?(validating width: Int, height: Int, pixels: [UInt8]) {
        guard width >= 0, height >= 0, pixels.count == width * height else { return nil }
        self.init(width: width, height: height, pixels: pixels)
    }

    public func luma(x: Int, y: Int) -> UInt8 {
        pixels[y * width + x]
    }

    /// Average brightness, used to pause detection once the yard goes dark.
    public var meanLuma: Double {
        guard !pixels.isEmpty else { return 0 }
        var total = 0
        for p in pixels { total += Int(p) }
        return Double(total) / Double(pixels.count)
    }
}
