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
}
