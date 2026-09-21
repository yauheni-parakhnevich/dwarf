import Foundation

/// A least-squares quadratic surface over normalised image coordinates:
/// `v = a0 + a1·x + a2·y + a3·x² + a4·x·y + a5·y²`.
///
/// Smooth, cheap, and sane a little outside the sampled area — which matters, because the
/// owner will not calibrate every corner of the yard.
public struct QuadraticFit: Equatable, Codable, Sendable {
    public let coefficients: [Double]   // exactly six

    public init?(coefficients: [Double]) {
        guard coefficients.count == 6 else { return nil }
        self.coefficients = coefficients
    }

    public func value(at p: Point) -> Double {
        let basis = QuadraticFit.basis(p)
        var sum = 0.0
        for i in 0..<6 { sum += coefficients[i] * basis[i] }
        return sum
    }

    public func residual(at p: Point, expected: Double) -> Double {
        abs(value(at: p) - expected)
    }

    static func basis(_ p: Point) -> [Double] {
        [1, p.x, p.y, p.x * p.x, p.x * p.y, p.y * p.y]
    }

    /// Fits the surface. Returns nil when there are fewer than six samples, or when they
    /// are laid out so the surface is not determined — all on one line, for instance.
    public static func fit(_ samples: [(Point, Double)]) -> QuadraticFit? {
        guard samples.count >= 6 else { return nil }

        // Normal equations: (AᵀA) c = Aᵀb.
        var ata = [[Double]](repeating: [Double](repeating: 0, count: 6), count: 6)
        var atb = [Double](repeating: 0, count: 6)

        for (point, value) in samples {
            let basis = basis(point)
            for i in 0..<6 {
                atb[i] += basis[i] * value
                for j in 0..<6 {
                    ata[i][j] += basis[i] * basis[j]
                }
            }
        }

        guard let solution = solve(ata, atb) else { return nil }
        return QuadraticFit(coefficients: solution)
    }

    /// Gaussian elimination with partial pivoting. Returns nil if the matrix is singular
    /// to within a tolerance, which is how a degenerate sample layout is detected.
    ///
    /// The `1e-12` pivot threshold is only correct because it is applied to `AᵀA`, built from
    /// image coordinates normalised to 0...1: every entry is a sum of at most a few dozen
    /// products of basis values already in that range, so entries stay bounded to roughly the
    /// sample count no matter how large the fitted pan, tilt or range values are — those enter
    /// only the right-hand side, never this matrix. That keeps `1e-12` many orders of magnitude
    /// below the smallest pivots seen even for tightly clustered real calibration layouts
    /// (measured down to ~1e-4), and comfortably above double-precision rounding noise on
    /// entries of that scale. If raw pixel coordinates or unnormalised ranges ever fed this
    /// matrix instead, entries could be arbitrarily large and a fixed absolute threshold like
    /// this one would stop meaning anything — it would need to scale with the matrix, e.g. as a
    /// tolerance relative to its norm.
    static func solve(_ matrix: [[Double]], _ rhs: [Double]) -> [Double]? {
        let n = rhs.count
        var a = matrix
        var b = rhs

        for column in 0..<n {
            var pivotRow = column
            var pivotValue = abs(a[column][column])
            for row in (column + 1)..<n where abs(a[row][column]) > pivotValue {
                pivotValue = abs(a[row][column])
                pivotRow = row
            }
            guard pivotValue > 1e-12 else { return nil }

            if pivotRow != column {
                a.swapAt(pivotRow, column)
                b.swapAt(pivotRow, column)
            }

            let pivot = a[column][column]
            for row in (column + 1)..<n {
                let factor = a[row][column] / pivot
                guard factor != 0 else { continue }
                for k in column..<n {
                    a[row][k] -= factor * a[column][k]
                }
                b[row] -= factor * b[column]
            }
        }

        var solution = [Double](repeating: 0, count: n)
        for row in stride(from: n - 1, through: 0, by: -1) {
            var sum = b[row]
            for k in (row + 1)..<n {
                sum -= a[row][k] * solution[k]
            }
            solution[row] = sum / a[row][row]
        }
        return solution.allSatisfy { $0.isFinite } ? solution : nil
    }
}
