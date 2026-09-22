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

/// What the aim is chasing. This is a label for logs and the UI, switching cleanly at
/// `Aimer.bodyHeadSplitM`; the tilt itself does not switch with it. See `bodyHeadBlendM`.
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
    /// True when this solution should not be fired on: see `flagReasons`.
    public let isFlagged: Bool
    /// The single most serious reason this solution is flagged, or nil when it is not.
    /// The most severe entry of `flagReasons`, kept as its own field so existing callers
    /// that only care about one reason do not need to change.
    public let flagReason: String?
    /// Every reason this solution is flagged, worst first: a non-finite fit result outranks
    /// being outside the servo limits, which outranks being outside the calibrated area,
    /// which outranks a missing height offset. A servo limit means the nozzle physically
    /// cannot reach the computed aim; a missing height sample is only a calibration chore
    /// that leaves a guess in its place. Empty when the solution is not flagged.
    public let flagReasons: [String]
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
    /// Range at which `target` switches from body to head, for logs and the UI.
    public var bodyHeadSplitM: Double = 4.0
    /// Width of the range band, centred on `bodyHeadSplitM`, across which the head's height
    /// offset is blended in rather than switched on. `Aimer` is a value type with no
    /// per-track state, so a target hovering near the split cannot be smoothed with
    /// hysteresis; blending the offset itself removes the jump instead of asking some other
    /// layer to hold state to hide it. Below `bodyHeadSplitM - bodyHeadBlendM / 2` the tilt
    /// is pure ground aim; at or above `bodyHeadSplitM + bodyHeadBlendM / 2` it carries the
    /// full offset; in between it carries that fraction of it, so the aim point rises
    /// smoothly through the shoulders rather than hopping from ground to head. `target`
    /// still switches labels at the midpoint, so a `.head` solution near the split can
    /// legitimately carry only a small fraction of the full offset - that is expected, not
    /// a bug.
    public var bodyHeadBlendM: Double = 0.4
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

        let blendFactor = headBlendFactor(forRange: range)
        var rawTilt = groundTilt
        var offsetMissing = false
        if blendFactor > 0 {
            if let offset = calibration.heightOffset(atRange: range) {
                rawTilt = groundTilt + blendFactor * offset
            } else {
                // Blending needed an offset and there isn't one: fall back to the pure
                // ground solution rather than guessing, and flag it below.
                offsetMissing = true
            }
        }

        var reasons: [String] = []

        // A non-finite result makes every other check meaningless for pan and tilt - a
        // comparison against NaN is neither true nor false in any useful sense - so it
        // stands alone rather than also reporting a vacuous "outside servo limits". The
        // calibrated-area and missing-offset checks below do not depend on these values
        // (they look at the input point and the range table), so they still apply.
        let nonFinite = !rawPan.isFinite || !rawTilt.isFinite || !range.isFinite
        if nonFinite {
            reasons.append("fit produced a non-finite value")
        } else if !limits.contains(pan: rawPan, tilt: rawTilt) {
            reasons.append("outside servo limits")
        }

        // The head point matters here exactly when it is the one doing the work: pan is
        // computed from it only when the target is the head, and that is also the case
        // where a stretched or merged box can push it somewhere never measured while the
        // ground point stays perfectly reasonable.
        let headOutside = target == .head && !isInsideCalibratedArea(headPoint)
        if !isInsideCalibratedArea(groundPoint) || headOutside {
            reasons.append("outside the calibrated area")
        }

        if offsetMissing {
            reasons.append("no height offset calibrated")
        }

        return AimSolution(
            pan: limits.clampPan(rawPan.isFinite ? rawPan : 0),
            tilt: limits.clampTilt(rawTilt.isFinite ? rawTilt : 0),
            rangeM: range.isFinite ? range : 0,
            target: target,
            isFlagged: !reasons.isEmpty,
            flagReason: reasons.first,
            flagReasons: reasons
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

    /// What fraction of the head's height offset applies at a given range: 0 at or below
    /// the bottom of the band, 1 at or above its top, ramped linearly in between. Checking
    /// the top of the band first keeps this consistent with `target` even when
    /// `bodyHeadBlendM` is 0: at exactly `bodyHeadSplitM`, `target` is already `.head`, and
    /// this returns 1 to match rather than 0.
    private func headBlendFactor(forRange range: Double) -> Double {
        let half = bodyHeadBlendM / 2
        let lower = bodyHeadSplitM - half
        let upper = bodyHeadSplitM + half
        if range >= upper { return 1 }
        if range <= lower { return 0 }
        guard upper > lower else { return 0 }
        return (range - lower) / (upper - lower)
    }

    /// The calibrated area is approximated by the bounding box of the sampled points plus
    /// a margin. A convex hull would be tighter, but the box is easy to reason about and
    /// errs toward flagging, which is the safe direction. Neither shape catches an interior
    /// gap - a corner of the box nobody actually walked to, such as a flowerbed skipped
    /// during calibration - since both only describe the outer extent of the samples. That
    /// is a real blind spot; the mitigation is `residuals()`, shown to the owner so they
    /// know where to add samples, not a tighter boundary shape.
    private func isInsideCalibratedArea(_ p: Point) -> Bool {
        p.x >= area.x - extrapolationMargin &&
        p.x <= area.x + area.width + extrapolationMargin &&
        p.y >= area.y - extrapolationMargin &&
        p.y <= area.y + area.height + extrapolationMargin
    }
}
