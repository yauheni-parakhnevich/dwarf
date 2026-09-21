import XCTest
@testable import DwarfCore

final class SchedulerTests: XCTestCase {
    private func blob(x: Double, y: Double) -> Blob {
        Blob(boundingBox: Rect(x: x, y: y, width: 0.05, height: 0.08), area: 50)
    }

    func testWithoutMotionItStillSweeps() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [])
        XCTAssertEqual(requests.count, 1)
        XCTAssertEqual(requests[0].kind, .sweep)
    }

    func testSweepTilesCycleAndCoverTheFrame() {
        let scheduler = Scheduler()   // default 2 columns x 1 row
        let first = scheduler.next(blobs: [])[0].rect
        let second = scheduler.next(blobs: [])[0].rect
        let third = scheduler.next(blobs: [])[0].rect

        XCTAssertNotEqual(first, second, "consecutive cycles must sweep different tiles")
        XCTAssertEqual(first, third, "two tiles means the cycle repeats on the third call")
        XCTAssertLessThan(first.x, second.x)
        // Together the tiles span the frame.
        XCTAssertEqual(first.x, 0, accuracy: 1e-9)
        XCTAssertEqual(second.x + second.width, 1, accuracy: 1e-9)
    }

    func testSweepTilesOverlap() {
        let scheduler = Scheduler()
        let left = scheduler.next(blobs: [])[0].rect
        let right = scheduler.next(blobs: [])[0].rect
        XCTAssertGreaterThan(left.x + left.width, right.x,
                             "tiles must overlap so a cat on the seam is not missed")
    }

    func testMotionCropsAreCentredOnBlobs() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [blob(x: 0.4, y: 0.4)])
        let crops = requests.filter { $0.kind == .motion }

        XCTAssertEqual(crops.count, 1)
        let expectedCentre = Point(x: 0.425, y: 0.44)
        XCTAssertEqual(crops[0].rect.center.x, expectedCentre.x, accuracy: 1e-6)
        XCTAssertEqual(crops[0].rect.center.y, expectedCentre.y, accuracy: 1e-6)
    }

    func testCropsAreClampedInsideTheFrame() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [blob(x: 0.97, y: 0.95)])
        let crop = requests.first { $0.kind == .motion }!.rect

        XCTAssertGreaterThanOrEqual(crop.x, 0)
        XCTAssertGreaterThanOrEqual(crop.y, 0)
        XCTAssertLessThanOrEqual(crop.x + crop.width, 1 + 1e-9)
        XCTAssertLessThanOrEqual(crop.y + crop.height, 1 + 1e-9)
    }

    func testMotionCropsAreCappedAndPreferLargerBlobs() {
        var config = SchedulerConfig()
        config.maxMotionCrops = 2
        let scheduler = Scheduler(config: config)

        let small = Blob(boundingBox: Rect(x: 0.1, y: 0.1, width: 0.02, height: 0.02), area: 25)
        let medium = Blob(boundingBox: Rect(x: 0.5, y: 0.5, width: 0.04, height: 0.04), area: 120)
        let large = Blob(boundingBox: Rect(x: 0.8, y: 0.2, width: 0.06, height: 0.06), area: 400)

        let crops = scheduler.next(blobs: [small, medium, large]).filter { $0.kind == .motion }
        XCTAssertEqual(crops.count, 2)
        // Largest first: the biggest moving thing is the most likely cat.
        XCTAssertEqual(crops[0].rect.center.x, large.boundingBox.center.x, accuracy: 0.05)
        XCTAssertEqual(crops[1].rect.center.x, medium.boundingBox.center.x, accuracy: 0.05)
    }

    func testABlobBiggerThanTheCropGrowsTheCrop() {
        let scheduler = Scheduler()
        let huge = Blob(boundingBox: Rect(x: 0.2, y: 0.2, width: 0.5, height: 0.5), area: 5000)
        let crop = scheduler.next(blobs: [huge]).first { $0.kind == .motion }!.rect

        XCTAssertGreaterThanOrEqual(crop.width, 0.5)
        XCTAssertGreaterThanOrEqual(crop.height, 0.5)
    }
}
