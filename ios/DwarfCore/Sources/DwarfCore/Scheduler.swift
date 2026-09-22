import Foundation

public struct SchedulerConfig: Equatable, Sendable {
    /// The model's input edge, in pixels. Kept in pixels rather than as a normalised
    /// fraction because "the model wants a square crop" is a fact about pixel space, not
    /// normalised space: whether a normalised rect comes out square in pixels depends
    /// entirely on the frame's actual resolution, which is why that resolution is spelled
    /// out below instead of being baked into a single normalised constant.
    public var cropPixels: Int = 640
    /// The capture size this scheduler is configured for. These must match what the camera
    /// actually produces — they exist only to convert `cropPixels` into the normalised
    /// units the rest of this type works in, so a crop really does come out square in
    /// pixels for whatever frame size the camera is producing.
    public var frameWidthPixels: Int = 1920
    public var frameHeightPixels: Int = 1080
    /// How many motion crops to spend per cycle. Slot one always goes to the largest blob;
    /// any remaining slots rotate through the rest so none of them is starved forever.
    public var maxMotionCrops: Int = 2
    /// Sweep grid. 2x1 covers a 1080p frame in two tiles of 960x1080.
    public var sweepColumns: Int = 2
    public var sweepRows: Int = 1
    /// Fraction of a tile that overlaps its neighbour, so a cat on the seam is still whole
    /// in at least one tile.
    public var sweepOverlap: Double = 0.12

    public init() {}

    /// Crop width in normalised units, derived from `cropPixels` and `frameWidthPixels`.
    /// Guarded against a non-positive dimension — which would otherwise divide by zero, or
    /// produce NaN if both were zero — and clamped into 0...1 since a crop can never be
    /// wider than the frame it is cut from.
    var cropWidth: Double {
        guard cropPixels > 0, frameWidthPixels > 0 else { return 0 }
        return min(1, Double(cropPixels) / Double(frameWidthPixels))
    }

    /// See `cropWidth`; the same derivation against the frame height.
    var cropHeight: Double {
        guard cropPixels > 0, frameHeightPixels > 0 else { return 0 }
        return min(1, Double(cropPixels) / Double(frameHeightPixels))
    }
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
    /// Where the rotation among non-largest blobs currently starts. See `select(from:)`.
    private var rotationOffset = 0

    public init(config: SchedulerConfig = SchedulerConfig()) {
        self.config = config
    }

    public func next(blobs: [Blob]) -> [CropRequest] {
        let sorted = blobs.sorted { $0.area > $1.area }
        var requests = select(from: sorted)
            .map { CropRequest(rect: crop(around: $0.boundingBox), kind: .motion) }

        requests.append(CropRequest(rect: sweepTile(), kind: .sweep))
        return requests
    }

    /// Chooses which blobs get a crop this cycle.
    ///
    /// The largest blob always gets a slot: it is the most likely cat, and the one most
    /// worth reacting to quickly. The scheduler has no way to recognise the *same* blob
    /// across cycles — there is no identity tracking here, deliberately — so the remaining
    /// slots instead rotate through the rest by their position in this cycle's sorted
    /// order. Given enough calls, every position gets a turn, which is what stops a blob
    /// that consistently ranks low from being starved forever.
    private func select(from sorted: [Blob]) -> [Blob] {
        let maxCrops = max(0, config.maxMotionCrops)
        guard maxCrops > 0, !sorted.isEmpty else { return [] }
        guard sorted.count > maxCrops else {
            // Fewer blobs than slots: everyone is served, every cycle.
            return sorted
        }

        let rest = Array(sorted.dropFirst())
        let remainingSlots = maxCrops - 1
        var selected = [sorted[0]]

        if remainingSlots > 0 {
            for i in 0..<remainingSlots {
                selected.append(rest[(rotationOffset + i) % rest.count])
            }
            rotationOffset = (rotationOffset + remainingSlots) % rest.count
        }
        return selected
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
