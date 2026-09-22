import XCTest
@testable import DwarfCore

final class QuadraticFitTests: XCTestCase {
    /// Samples a known surface on a grid, so the fit has something exact to recover.
    private func samples(_ f: (Double, Double) -> Double) -> [(Point, Double)] {
        var out: [(Point, Double)] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.1, through: 0.9, by: 0.2) {
                out.append((Point(x: x, y: y), f(x, y)))
            }
        }
        return out
    }

    func testRecoversAPlane() throws {
        let fit = try XCTUnwrap(QuadraticFit.fit(samples { x, y in 3 + 2 * x - 5 * y }))
        XCTAssertEqual(fit.value(at: Point(x: 0.5, y: 0.5)), 3 + 1 - 2.5, accuracy: 1e-6)
        XCTAssertEqual(fit.value(at: Point(x: 0.2, y: 0.7)), 3 + 0.4 - 3.5, accuracy: 1e-6)
    }

    func testRecoversACurvedSurface() throws {
        let f: (Double, Double) -> Double = { x, y in 1 + 2 * x - 3 * y + 4 * x * x + 5 * x * y - 6 * y * y }
        let fit = try XCTUnwrap(QuadraticFit.fit(samples(f)))
        XCTAssertEqual(fit.value(at: Point(x: 0.35, y: 0.65)), f(0.35, 0.65), accuracy: 1e-6)
    }

    func testToleratesNoisySamples() throws {
        var noisy = samples { x, y in 10 + 4 * x - 2 * y }
        noisy[3].1 += 0.05
        noisy[7].1 -= 0.04
        let fit = try XCTUnwrap(QuadraticFit.fit(noisy))
        XCTAssertEqual(fit.value(at: Point(x: 0.5, y: 0.5)), 11, accuracy: 0.1)
    }

    func testTooFewPointsReturnsNil() {
        let five = Array(samples { x, _ in x }.prefix(5))
        XCTAssertNil(QuadraticFit.fit(five))
    }

    func testDegenerateLayoutReturnsNil() {
        // Every sample on one line: the surface is not determined.
        let collinear = (0..<10).map { i -> (Point, Double) in
            let t = Double(i) / 10
            return (Point(x: t, y: t), t)
        }
        XCTAssertNil(QuadraticFit.fit(collinear))
    }

    func testResidualReportsFitError() throws {
        let fit = try XCTUnwrap(QuadraticFit.fit(samples { x, y in x + y }))
        XCTAssertEqual(fit.residual(at: Point(x: 0.4, y: 0.4), expected: 0.8), 0, accuracy: 1e-6)
        XCTAssertEqual(fit.residual(at: Point(x: 0.4, y: 0.4), expected: 1.0), 0.2, accuracy: 1e-6)
    }
}
