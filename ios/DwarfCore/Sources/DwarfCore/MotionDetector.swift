import Foundation

public struct MotionConfig: Equatable, Sendable {
    /// How fast the background forgets. Higher absorbs a stopped object sooner.
    public var backgroundAlpha: Double = 0.05
    /// Absolute luma difference that counts as movement.
    public var threshold: Double = 25
    /// Blobs smaller than this many pixels are noise: leaves, rain, sensor grain.
    public var minBlobArea: Int = 20
    /// Grows each blob by this many pixels, closing the gaps inside one moving subject.
    public var dilationRadius: Int = 1

    public init() {}
}

public struct Blob: Equatable, Sendable {
    public let boundingBox: Rect
    public let area: Int

    public init(boundingBox: Rect, area: Int) {
        self.boundingBox = boundingBox
        self.area = area
    }
}

/// Finds moving regions by comparing each frame against a running average of the ones
/// before it.
///
/// Deliberately generous: its output only decides where the detector looks, and a missed
/// blob is covered by the Scheduler's sweep tiles.
public final class MotionDetector {
    public var config: MotionConfig
    private var background: [Double]?
    private var backgroundSize: (width: Int, height: Int)?

    public init(config: MotionConfig = MotionConfig()) {
        self.config = config
    }

    /// Forget the learned background. The next frame becomes the new one.
    public func reset() {
        background = nil
        backgroundSize = nil
    }

    public func process(_ frame: GrayFrame) -> [Blob] {
        guard frame.width > 0, frame.height > 0 else { return [] }

        // First frame, or the resolution changed: adopt it as the background and report
        // nothing. Reporting movement here would make every start-up a false alarm.
        guard var bg = background,
              let size = backgroundSize,
              size.width == frame.width, size.height == frame.height else {
            background = frame.pixels.map(Double.init)
            backgroundSize = (frame.width, frame.height)
            return []
        }

        var moving = [Bool](repeating: false, count: frame.pixels.count)
        for i in frame.pixels.indices {
            let value = Double(frame.pixels[i])
            moving[i] = abs(value - bg[i]) >= config.threshold
            bg[i] += config.backgroundAlpha * (value - bg[i])
        }
        background = bg

        let dilated = dilate(moving, width: frame.width, height: frame.height,
                             radius: config.dilationRadius)
        return components(dilated, width: frame.width, height: frame.height)
            .filter { $0.area >= config.minBlobArea }
    }

    private func dilate(_ mask: [Bool], width: Int, height: Int, radius: Int) -> [Bool] {
        guard radius > 0 else { return mask }
        var out = [Bool](repeating: false, count: mask.count)
        for y in 0..<height {
            for x in 0..<width where mask[y * width + x] {
                let yLow = max(0, y - radius), yHigh = min(height - 1, y + radius)
                let xLow = max(0, x - radius), xHigh = min(width - 1, x + radius)
                for yy in yLow...yHigh {
                    for xx in xLow...xHigh {
                        out[yy * width + xx] = true
                    }
                }
            }
        }
        return out
    }

    /// Four-connected labelling with an explicit stack: recursion would blow up on a blob
    /// covering a large part of the frame.
    private func components(_ mask: [Bool], width: Int, height: Int) -> [Blob] {
        var visited = [Bool](repeating: false, count: mask.count)
        var blobs: [Blob] = []
        var stack: [Int] = []

        for start in mask.indices where mask[start] && !visited[start] {
            visited[start] = true
            stack.removeAll(keepingCapacity: true)
            stack.append(start)

            var minX = width, maxX = -1, minY = height, maxY = -1, area = 0

            while let index = stack.popLast() {
                let x = index % width
                let y = index / width
                area += 1
                minX = min(minX, x); maxX = max(maxX, x)
                minY = min(minY, y); maxY = max(maxY, y)

                if x > 0 { push(index - 1, &stack, &visited, mask) }
                if x < width - 1 { push(index + 1, &stack, &visited, mask) }
                if y > 0 { push(index - width, &stack, &visited, mask) }
                if y < height - 1 { push(index + width, &stack, &visited, mask) }
            }

            blobs.append(Blob(
                boundingBox: Rect(
                    x: Double(minX) / Double(width),
                    y: Double(minY) / Double(height),
                    width: Double(maxX - minX + 1) / Double(width),
                    height: Double(maxY - minY + 1) / Double(height)
                ),
                area: area
            ))
        }
        return blobs
    }

    private func push(_ index: Int, _ stack: inout [Int], _ visited: inout [Bool], _ mask: [Bool]) {
        guard mask[index], !visited[index] else { return }
        visited[index] = true
        stack.append(index)
    }
}
