import Foundation

/// Mechanical travel limits. These must stay inside the printed hard stops, never the
/// other way round.
public struct AimLimits: Equatable, Codable, Sendable {
    public var panMin: Double = -60
    public var panMax: Double = 60
    public var tiltMin: Double = -30
    public var tiltMax: Double = 40

    public init() {}

    public func clampPan(_ v: Double) -> Double { min(max(v, panMin), panMax) }
    public func clampTilt(_ v: Double) -> Double { min(max(v, tiltMin), tiltMax) }
    public func contains(pan: Double, tilt: Double) -> Bool {
        pan >= panMin && pan <= panMax && tilt >= tiltMin && tilt <= tiltMax
    }
}

public enum AimTarget: String, Equatable, Sendable {
    /// Between 2 and 4 m, where the jet is still a hard stream.
    case body
    /// Beyond 4 m, where it arrives as spread spray.
    case head
}

public struct AimSolution: Equatable, Sendable {
    public let pan: Double
    public let tilt: Double
    public let rangeM: Double
    public let target: AimTarget
    /// True when this solution should not be fired on: outside the servo limits, outside
    /// the calibrated area, or a head shot with no height data behind it.
    public let isFlagged: Bool
    public let flagReason: String?
}

public struct AimerResidual: Equatable, Sendable {
    public let point: CalibrationPoint
    public let panError: Double
    public let tiltError: Double
    public let rangeError: Double
}

/// Maps an image point to servo angles, using only what was measured on the lawn.
public struct Aimer {
    public let limits: AimLimits
    /// Range at which aim moves from the body to the head.
    public var bodyHeadSplitM: Double = 4.0
    /// How far outside the calibrated area a point may sit before its solution is flagged.
    public var extrapolationMargin: Double = 0.08

    private let calibration: Calibration
    private let panFit: QuadraticFit
    private let tiltFit: QuadraticFit
    private let rangeFit: QuadraticFit
    private let area: Rect

    /// Nil when the calibration cannot support a fit: fewer than six points, or a
    /// degenerate layout such as every point on one line.
    public init?(calibration: Calibration, limits: AimLimits = AimLimits()) {
        guard let pan = QuadraticFit.fit(calibration.points.map { ($0.image, $0.pan) }),
              let tilt = QuadraticFit.fit(calibration.points.map { ($0.image, $0.tilt) }),
              let range = QuadraticFit.fit(calibration.points.map { ($0.image, $0.rangeM) })
        else { return nil }

        let xs = calibration.points.map(\.image.x)
        let ys = calibration.points.map(\.image.y)
        guard let minX = xs.min(), let maxX = xs.max(),
              let minY = ys.min(), let maxY = ys.max() else { return nil }

        self.calibration = calibration
        self.limits = limits
        self.panFit = pan
        self.tiltFit = tilt
        self.rangeFit = range
        self.area = Rect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
    }

    public func solve(for track: Track) -> AimSolution {
        solve(groundPoint: track.groundPoint, headPoint: track.headPoint)
    }

    public func solve(groundPoint: Point, headPoint: Point) -> AimSolution {
        let range = rangeFit.value(at: groundPoint)
        let target: AimTarget = range >= bodyHeadSplitM ? .head : .body

        // Pan comes from the point being aimed at; tilt always starts from the ground
        // solution, because that is what the calibration measured.
        let rawPan = panFit.value(at: target == .head ? headPoint : groundPoint)
        let groundTilt = tiltFit.value(at: groundPoint)

        var reason: String?
        var rawTilt = groundTilt

        if target == .head {
            if let offset = calibration.heightOffset(atRange: range) {
                rawTilt = groundTilt + offset
            } else {
                reason = "no height offset calibrated"
            }
        }

        if !isInsideCalibratedArea(groundPoint) {
            reason = reason ?? "outside the calibrated area"
        }
        if !limits.contains(pan: rawPan, tilt: rawTilt) {
            reason = reason ?? "outside servo limits"
        }
        if !rawPan.isFinite || !rawTilt.isFinite || !range.isFinite {
            reason = "fit produced a non-finite value"
        }

        return AimSolution(
            pan: limits.clampPan(rawPan.isFinite ? rawPan : 0),
            tilt: limits.clampTilt(rawTilt.isFinite ? rawTilt : 0),
            rangeM: range.isFinite ? range : 0,
            target: target,
            isFlagged: reason != nil,
            flagReason: reason
        )
    }

    /// How well the fit reproduces each calibration point. The web UI shows this so the
    /// owner knows where to add samples.
    public func residuals() -> [AimerResidual] {
        calibration.points.map { point in
            AimerResidual(
                point: point,
                panError: panFit.residual(at: point.image, expected: point.pan),
                tiltError: tiltFit.residual(at: point.image, expected: point.tilt),
                rangeError: rangeFit.residual(at: point.image, expected: point.rangeM)
            )
        }
    }

    /// The calibrated area is approximated by the bounding box of the sampled points plus
    /// a margin. A convex hull would be tighter, but the box is easy to reason about and
    /// errs toward flagging, which is the safe direction.
    private func isInsideCalibratedArea(_ p: Point) -> Bool {
        p.x >= area.x - extrapolationMargin &&
        p.x <= area.x + area.width + extrapolationMargin &&
        p.y >= area.y - extrapolationMargin &&
        p.y <= area.y + area.height + extrapolationMargin
    }
}
