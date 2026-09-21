import Foundation

public struct SchedulerConfig: Equatable, Sendable {
    /// Crop size in normalised units. The defaults are a 640x640 pixel crop taken from a
    /// 1920x1080 frame, which is why they differ: 640/1920 wide, 640/1080 tall.
    public var cropWidth: Double = 640.0 / 1920.0
    public var cropHeight: Double = 640.0 / 1080.0
    /// How many motion crops to spend per cycle, largest blob first.
    public var maxMotionCrops: Int = 2
    /// Sweep grid. 2x1 covers a 1080p frame in two tiles of 960x1080.
    public var sweepColumns: Int = 2
    public var sweepRows: Int = 1
    /// Fraction of a tile that overlaps its neighbour, so a cat on the seam is still whole
    /// in at least one tile.
    public var sweepOverlap: Double = 0.12

    public init() {}
}

public struct CropRequest: Equatable, Sendable {
    public enum Kind: Equatable, Sendable {
        /// Something moved here this cycle.
        case motion
        /// Part of the rolling full-frame sweep.
        case sweep
    }

    public let rect: Rect
    public let kind: Kind

    public init(rect: Rect, kind: Kind) {
        self.rect = rect
        self.kind = kind
    }
}

/// Chooses what the detector looks at this cycle.
///
/// Motion crops react fast to a walking cat. The sweep is slower but finds a cat that has
/// stopped: once it stops moving, the motion detector's background absorbs it within
/// seconds and it would otherwise become invisible.
public final class Scheduler {
    public var config: SchedulerConfig
    private var nextTile = 0

    public init(config: SchedulerConfig = SchedulerConfig()) {
        self.config = config
    }

    public func next(blobs: [Blob]) -> [CropRequest] {
        var requests = blobs
            .sorted { $0.area > $1.area }
            .prefix(max(0, config.maxMotionCrops))
            .map { CropRequest(rect: crop(around: $0.boundingBox), kind: .motion) }

        requests.append(CropRequest(rect: sweepTile(), kind: .sweep))
        return requests
    }

    /// A crop centred on the blob, at least as large as the configured crop, grown if the
    /// blob itself is bigger, and clamped to the frame.
    private func crop(around box: Rect) -> Rect {
        let width = min(1, max(config.cropWidth, box.width))
        let height = min(1, max(config.cropHeight, box.height))
        let centre = box.center
        let x = min(max(0, centre.x - width / 2), 1 - width)
        let y = min(max(0, centre.y - height / 2), 1 - height)
        return Rect(x: x, y: y, width: width, height: height)
    }

    private func sweepTile() -> Rect {
        let columns = max(1, config.sweepColumns)
        let rows = max(1, config.sweepRows)
        let count = columns * rows
        let index = nextTile % count
        nextTile = (nextTile + 1) % count

        let column = index % columns
        let row = index / columns

        let baseWidth = 1.0 / Double(columns)
        let baseHeight = 1.0 / Double(rows)
        let width = min(1, baseWidth * (1 + config.sweepOverlap))
        let height = min(1, baseHeight * (1 + config.sweepOverlap))

        // Spread the tiles so the first starts at 0 and the last ends at 1, with the
        // overlap absorbed in between.
        let xSpan = columns > 1 ? (1 - width) / Double(columns - 1) : 0
        let ySpan = rows > 1 ? (1 - height) / Double(rows - 1) : 0

        return Rect(x: Double(column) * xSpan, y: Double(row) * ySpan,
                    width: width, height: height)
    }
}
