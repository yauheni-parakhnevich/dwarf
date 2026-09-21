import Foundation

/// A point in normalised frame coordinates: 0...1 across the frame, origin top-left.
/// Normalised rather than pixels so the logic — and any saved calibration — survives a
/// change of capture resolution.
public struct Point: Equatable, Codable, Sendable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }

    public func distance(to other: Point) -> Double {
        let dx = x - other.x
        let dy = y - other.y
        return (dx * dx + dy * dy).squareRoot()
    }
}

/// A rectangle in normalised frame coordinates.
public struct Rect: Equatable, Codable, Sendable {
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double

    public init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    public var center: Point { Point(x: x + width / 2, y: y + height / 2) }

    /// Where the subject meets the ground. This is the aiming key: the ground plane is
    /// fixed, so one ground point maps to exactly one pan/tilt pair.
    public var bottomCenter: Point { Point(x: x + width / 2, y: y + height) }

    /// Roughly where a cat's head is, used for aim beyond 4 m.
    public var topCenter: Point { Point(x: x + width / 2, y: y) }
}

/// A closed polygon in normalised coordinates, used for mask zones.
public struct Polygon: Equatable, Codable, Sendable {
    public var points: [Point]

    public init(points: [Point]) {
        self.points = points
    }

    /// Ray casting, which handles concave shapes correctly — a yard mask is rarely convex.
    public func contains(_ p: Point) -> Bool {
        guard points.count >= 3 else { return false }
        var inside = false
        var j = points.count - 1
        for i in points.indices {
            let a = points[i]
            let b = points[j]
            if (a.y > p.y) != (b.y > p.y) {
                let t = (p.y - a.y) / (b.y - a.y)
                if p.x < a.x + t * (b.x - a.x) { inside.toggle() }
            }
            j = i
        }
        return inside
    }
}
