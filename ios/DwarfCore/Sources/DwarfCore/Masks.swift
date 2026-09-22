import Foundation

/// Zones the owner draws over the camera view.
public struct MaskSet: Equatable, Codable, Sendable {
    /// Movement inside these is discarded before it reaches the detector: a road, a tree
    /// that sways, a neighbour's window.
    public var ignoreZones: [Polygon]
    /// Never fire at anything standing here. Chiefly the ground within about 2 m of the
    /// gnome, where the jet is still a hard stream rather than spread spray.
    public var noFireZones: [Polygon]
    /// Extra safety border around every no-fire zone, in normalised frame units. Boundary
    /// inclusion in `Polygon.contains` falls out of the geometry (top/left inclusive,
    /// bottom/right exclusive) rather than out of policy, so without a margin "exactly on the
    /// line" would be protected on some edges of a zone and not on others. The margin makes
    /// every edge behave the same: close enough counts as inside. Default is about half a
    /// percent of frame width — cheap insurance, not a real distance.
    public var noFireMargin: Double

    public init(ignoreZones: [Polygon] = [], noFireZones: [Polygon] = [], noFireMargin: Double = 0.005) {
        self.ignoreZones = ignoreZones
        self.noFireZones = noFireZones
        self.noFireMargin = noFireMargin
    }

    public static let empty = MaskSet()

    /// A non-finite point here fails open (not ignored): ignoring is only ever a convenience,
    /// so when a coordinate can't be trusted the safe default is to keep processing the
    /// detection rather than silently discard it.
    public func isIgnored(_ point: Point) -> Bool {
        ignoreZones.contains { $0.contains(point) }
    }

    /// Never fires at a point this returns true for. A no-fire zone is a safety mechanism, so
    /// every uncertain case must fail closed (protected), unlike `isIgnored`.
    public func isNoFire(_ point: Point) -> Bool {
        // An unreadable position is exactly when not firing is correct — we cannot know it's
        // safe, and a stray NaN/inf must never read as "no zone contains this".
        guard point.x.isFinite, point.y.isFinite else { return true }
        for zone in noFireZones {
            if zone.contains(point) { return true }
            if Self.distance(from: point, toEdgesOf: zone) <= noFireMargin { return true }
        }
        return false
    }

    /// Every problem found in the zones, for a web UI to surface to the owner. This never
    /// changes what `isIgnored`/`isNoFire` decide — a degenerate zone still evaluates exactly as
    /// it does today — it only makes "this no-fire zone currently protects nothing" visible
    /// instead of silent.
    public func validate() -> [MaskIssue] {
        var issues: [MaskIssue] = []
        Self.validate(ignoreZones, kind: .ignore, into: &issues)
        Self.validate(noFireZones, kind: .noFire, into: &issues)
        return issues
    }

    private static func validate(_ zones: [Polygon], kind: MaskIssue.Kind, into issues: inout [MaskIssue]) {
        for (index, zone) in zones.enumerated() {
            let points = zone.points
            if points.contains(where: { !$0.x.isFinite || !$0.y.isFinite }) {
                issues.append(.nonFiniteCoordinate(zone: index, kind: kind))
            }
            guard points.count >= 3 else {
                issues.append(.tooFewPoints(zone: index, kind: kind))
                continue
            }
            if abs(signedArea(of: points)) < areaEpsilon {
                issues.append(.degenerateArea(zone: index, kind: kind))
            }
        }
    }

    /// Shoelace formula. Used only to catch a collapsed outline (a click without a drag, or
    /// points that all lie on one line) — the sign, which distinguishes winding direction,
    /// is irrelevant here.
    private static func signedArea(of points: [Point]) -> Double {
        var sum = 0.0
        for i in points.indices {
            let a = points[i]
            let b = points[(i + 1) % points.count]
            sum += a.x * b.y - b.x * a.y
        }
        return sum / 2
    }

    private static let areaEpsilon = 1e-9

    /// Distance from a point to the nearest edge of a polygon, used for the no-fire margin.
    /// Fewer than two points means there is no edge to be near.
    private static func distance(from point: Point, toEdgesOf polygon: Polygon) -> Double {
        let points = polygon.points
        guard points.count >= 2 else { return .infinity }
        var nearest = Double.infinity
        var j = points.count - 1
        for i in points.indices {
            nearest = min(nearest, distance(from: point, toSegment: points[i], points[j]))
            j = i
        }
        return nearest
    }

    /// Point-to-segment distance. A zone with duplicate consecutive points (an easy stray
    /// click in the web UI) yields a zero-length segment; falling back to point-to-point
    /// distance avoids dividing by zero rather than special-casing the caller.
    private static func distance(from point: Point, toSegment a: Point, _ b: Point) -> Double {
        let dx = b.x - a.x
        let dy = b.y - a.y
        let lengthSquared = dx * dx + dy * dy
        guard lengthSquared > 0 else { return point.distance(to: a) }
        let t = max(0, min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / lengthSquared))
        let projection = Point(x: a.x + t * dx, y: a.y + t * dy)
        return point.distance(to: projection)
    }
}

/// A problem found in a `MaskSet`'s zones — reported, never thrown, so a caller (the web UI)
/// can tell the owner "this zone doesn't do what you think" without the app refusing to run.
public enum MaskIssue: Equatable, Sendable {
    /// Fewer than three points: no polygon, so `contains` always reports false.
    case tooFewPoints(zone: Int, kind: Kind)
    /// Three or more points but (near) zero enclosed area: a click without a drag, or points
    /// that collapsed onto a line.
    case degenerateArea(zone: Int, kind: Kind)
    /// A coordinate that is NaN or infinite, most likely a UI or transport bug.
    case nonFiniteCoordinate(zone: Int, kind: Kind)

    public enum Kind: Equatable, Sendable {
        case ignore
        case noFire
    }
}
