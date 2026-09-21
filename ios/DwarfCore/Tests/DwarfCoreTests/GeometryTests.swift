import XCTest
@testable import DwarfCore

final class GeometryTests: XCTestCase {
    func testRectDerivedPoints() {
        let r = Rect(x: 0.2, y: 0.4, width: 0.4, height: 0.2)
        XCTAssertEqual(r.center.x, 0.4, accuracy: 1e-9)
        XCTAssertEqual(r.center.y, 0.5, accuracy: 1e-9)
        XCTAssertEqual(r.bottomCenter.y, 0.6, accuracy: 1e-9)
        XCTAssertEqual(r.topCenter.y, 0.4, accuracy: 1e-9)
        XCTAssertEqual(r.bottomCenter.x, 0.4, accuracy: 1e-9)
    }

    func testPointDistance() {
        XCTAssertEqual(Point(x: 0, y: 0).distance(to: Point(x: 0.3, y: 0.4)), 0.5, accuracy: 1e-9)
    }

    func testPolygonContainment() {
        let square = Polygon(points: [
            Point(x: 0.2, y: 0.2), Point(x: 0.8, y: 0.2),
            Point(x: 0.8, y: 0.8), Point(x: 0.2, y: 0.8)
        ])
        XCTAssertTrue(square.contains(Point(x: 0.5, y: 0.5)))
        XCTAssertFalse(square.contains(Point(x: 0.1, y: 0.5)))
        XCTAssertFalse(square.contains(Point(x: 0.5, y: 0.9)))
    }

    func testConcavePolygonContainment() {
        // An L shape: the notch must not count as inside.
        let l = Polygon(points: [
            Point(x: 0.1, y: 0.1), Point(x: 0.5, y: 0.1), Point(x: 0.5, y: 0.5),
            Point(x: 0.9, y: 0.5), Point(x: 0.9, y: 0.9), Point(x: 0.1, y: 0.9)
        ])
        XCTAssertTrue(l.contains(Point(x: 0.2, y: 0.2)))
        XCTAssertTrue(l.contains(Point(x: 0.7, y: 0.7)))
        XCTAssertFalse(l.contains(Point(x: 0.7, y: 0.2)))
    }

    func testEmptyPolygonContainsNothing() {
        XCTAssertFalse(Polygon(points: []).contains(Point(x: 0.5, y: 0.5)))
    }
}
