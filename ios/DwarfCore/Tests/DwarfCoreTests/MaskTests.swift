import XCTest
@testable import DwarfCore

final class MaskTests: XCTestCase {
    private var masks: MaskSet {
        MaskSet(
            ignoreZones: [Polygon(points: [
                Point(x: 0, y: 0), Point(x: 0.3, y: 0), Point(x: 0.3, y: 0.3), Point(x: 0, y: 0.3)
            ])],
            noFireZones: [Polygon(points: [
                Point(x: 0, y: 0.85), Point(x: 1, y: 0.85), Point(x: 1, y: 1), Point(x: 0, y: 1)
            ])]
        )
    }

    func testIgnoreZone() {
        XCTAssertTrue(masks.isIgnored(Point(x: 0.1, y: 0.1)))
        XCTAssertFalse(masks.isIgnored(Point(x: 0.5, y: 0.5)))
    }

    func testNoFireZone() {
        XCTAssertTrue(masks.isNoFire(Point(x: 0.5, y: 0.95)))
        XCTAssertFalse(masks.isNoFire(Point(x: 0.5, y: 0.5)))
    }

    func testZonesAreIndependent() {
        XCTAssertFalse(masks.isIgnored(Point(x: 0.5, y: 0.95)))
        XCTAssertFalse(masks.isNoFire(Point(x: 0.1, y: 0.1)))
    }

    func testEmptyMaskSetAllowsEverything() {
        let empty = MaskSet.empty
        XCTAssertFalse(empty.isIgnored(Point(x: 0.5, y: 0.5)))
        XCTAssertFalse(empty.isNoFire(Point(x: 0.5, y: 0.5)))
    }

    func testRoundTripsThroughJSON() throws {
        let data = try JSONEncoder().encode(masks)
        let decoded = try JSONDecoder().decode(MaskSet.self, from: data)
        XCTAssertEqual(decoded, masks)
    }

    func testNonFinitePointIsNoFireButNotIgnored() {
        let nan = Point(x: Double.nan, y: 0.5)
        let inf = Point(x: 0.5, y: Double.infinity)
        XCTAssertTrue(masks.isNoFire(nan))
        XCTAssertTrue(masks.isNoFire(inf))
        XCTAssertFalse(masks.isIgnored(nan))
        XCTAssertFalse(masks.isIgnored(inf))
    }

    func testNoFireMarginCoversEveryEdgeOfARectangle() {
        // Before the margin, ray casting made the top and left edges of this rectangle "inside"
        // and the bottom and right edges "outside" — an accident of geometry, not policy. The
        // margin makes all four behave the same.
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0, y: 0.85), Point(x: 1, y: 0.85), Point(x: 1, y: 1), Point(x: 0, y: 1)
        ])])
        XCTAssertTrue(zone.isNoFire(Point(x: 0.5, y: 0.85))) // top edge (previously inside)
        XCTAssertTrue(zone.isNoFire(Point(x: 0, y: 0.9)))    // left edge (previously inside)
        XCTAssertTrue(zone.isNoFire(Point(x: 1, y: 0.9)))    // right edge (previously outside)
        XCTAssertTrue(zone.isNoFire(Point(x: 0.5, y: 1)))    // bottom edge (previously outside)
    }

    func testPointJustOutsideTheMarginIsNotNoFire() {
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0, y: 0.85), Point(x: 1, y: 0.85), Point(x: 1, y: 1), Point(x: 0, y: 1)
        ])])
        // 0.01 above the top edge: further than the default 0.005 margin.
        XCTAssertFalse(zone.isNoFire(Point(x: 0.5, y: 0.84)))
    }

    func testZeroLengthSegmentDoesNotCrashTheDistanceHelper() {
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0.5, y: 0.5), Point(x: 0.5, y: 0.5), Point(x: 0.6, y: 0.5), Point(x: 0.6, y: 0.6)
        ])])
        // A duplicate consecutive point makes one edge zero-length; the point is that this
        // returns at all, without dividing by zero.
        XCTAssertFalse(zone.isNoFire(Point(x: 0.1, y: 0.1)))
        XCTAssertTrue(zone.isNoFire(Point(x: 0.5, y: 0.5)))
    }

    func testValidateReportsDegenerateZonesWithKindAndIndex() {
        let broken = MaskSet(
            ignoreZones: [
                Polygon(points: [Point(x: 0, y: 0), Point(x: 1, y: 1)]) // too few points
            ],
            noFireZones: [
                Polygon(points: [ // healthy, index 0
                    Point(x: 0, y: 0.85), Point(x: 1, y: 0.85), Point(x: 1, y: 1), Point(x: 0, y: 1)
                ]),
                Polygon(points: [ // collapsed to a point, index 1
                    Point(x: 0.5, y: 0.5), Point(x: 0.5, y: 0.5), Point(x: 0.5, y: 0.5)
                ]),
                Polygon(points: [ // NaN coordinate, index 2
                    Point(x: 0, y: 0), Point(x: .nan, y: 0), Point(x: 1, y: 1)
                ])
            ]
        )
        let issues = broken.validate()
        XCTAssertTrue(issues.contains(.tooFewPoints(zone: 0, kind: .ignore)))
        XCTAssertTrue(issues.contains(.degenerateArea(zone: 1, kind: .noFire)))
        XCTAssertTrue(issues.contains(.nonFiniteCoordinate(zone: 2, kind: .noFire)))
        XCTAssertEqual(issues.count, 3)
    }

    func testValidateReturnsEmptyForAHealthyFixture() {
        XCTAssertEqual(masks.validate(), [])
    }
}
