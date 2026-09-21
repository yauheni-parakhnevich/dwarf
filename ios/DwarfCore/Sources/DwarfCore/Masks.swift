import Foundation

/// Zones the owner draws over the camera view.
public struct MaskSet: Equatable, Codable, Sendable {
    /// Movement inside these is discarded before it reaches the detector: a road, a tree
    /// that sways, a neighbour's window.
    public var ignoreZones: [Polygon]
    /// Never fire at anything standing here. Chiefly the ground within about 2 m of the
    /// gnome, where the jet is still a hard stream rather than spread spray.
    public var noFireZones: [Polygon]

    public init(ignoreZones: [Polygon] = [], noFireZones: [Polygon] = []) {
        self.ignoreZones = ignoreZones
        self.noFireZones = noFireZones
    }

    public static let empty = MaskSet()

    public func isIgnored(_ point: Point) -> Bool {
        ignoreZones.contains { $0.contains(point) }
    }

    public func isNoFire(_ point: Point) -> Bool {
        noFireZones.contains { $0.contains(point) }
    }
}
