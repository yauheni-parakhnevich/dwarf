import Foundation

/// One calibration shot: the owner fired at a spot, clicked where the water landed, and
/// typed how far away it was.
public struct CalibrationPoint: Equatable, Codable, Sendable {
    public var image: Point
    public var pan: Double
    public var tilt: Double
    public var rangeM: Double

    public init(image: Point, pan: Double, tilt: Double, rangeM: Double) {
        self.image = image
        self.pan = pan
        self.tilt = tilt
        self.rangeM = rangeM
    }
}

/// How much extra tilt raises the impact point by 25 cm at a given range — the difference
/// between hitting the ground under a cat and hitting the cat.
public struct HeightOffsetSample: Equatable, Codable, Sendable {
    public var rangeM: Double
    public var deltaTiltDeg: Double

    public init(rangeM: Double, deltaTiltDeg: Double) {
        self.rangeM = rangeM
        self.deltaTiltDeg = deltaTiltDeg
    }
}

/// Everything learned on the lawn, persisted as JSON by the iOS layer.
public struct Calibration: Equatable, Codable, Sendable {
    public var points: [CalibrationPoint]
    public var heightOffsets: [HeightOffsetSample]

    public init(points: [CalibrationPoint] = [], heightOffsets: [HeightOffsetSample] = []) {
        self.points = points
        self.heightOffsets = heightOffsets
    }

    public static let empty = Calibration()

    /// Linear interpolation by range, clamped at both ends. Nil when nothing was measured,
    /// which makes head aim impossible and is treated as such by the Aimer.
    public func heightOffset(atRange range: Double) -> Double? {
        let sorted = heightOffsets.sorted { $0.rangeM < $1.rangeM }
        guard let first = sorted.first, let last = sorted.last else { return nil }
        if range <= first.rangeM { return first.deltaTiltDeg }
        if range >= last.rangeM { return last.deltaTiltDeg }

        for (low, high) in zip(sorted, sorted.dropFirst()) where range >= low.rangeM && range <= high.rangeM {
            let span = high.rangeM - low.rangeM
            guard span > 0 else { return low.deltaTiltDeg }
            let t = (range - low.rangeM) / span
            return low.deltaTiltDeg + t * (high.deltaTiltDeg - low.deltaTiltDeg)
        }
        return last.deltaTiltDeg
    }
}
