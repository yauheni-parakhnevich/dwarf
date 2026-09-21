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

    // MARK: - Blob rotation

    // All centred on y = 0.5 and kept well clear of the frame edges (the default crop is
    // ~0.33 wide and ~0.59 tall, so a blob nearer an edge than half of that would have its
    // crop clamped and its centre shifted, which would break identifying blobs by centre.x).
    private let rotationLarge = Blob(boundingBox: Rect(x: 0.7, y: 0.5, width: 0.05, height: 0.05), area: 300)
    private let rotationMedium = Blob(boundingBox: Rect(x: 0.5, y: 0.5, width: 0.05, height: 0.05), area: 200)
    private let rotationSmall = Blob(boundingBox: Rect(x: 0.3, y: 0.5, width: 0.05, height: 0.05), area: 100)

    private func motionCentres(_ requests: [CropRequest]) -> [Double] {
        requests.filter { $0.kind == .motion }.map { $0.rect.center.x }
    }

    func testRotationAlwaysServesTheLargestBlob() {
        var config = SchedulerConfig()
        config.maxMotionCrops = 2
        let scheduler = Scheduler(config: config)
        let blobs = [rotationSmall, rotationMedium, rotationLarge]

        for cycle in 0..<4 {
            let centres = motionCentres(scheduler.next(blobs: blobs))
            XCTAssertTrue(centres.contains { abs($0 - rotationLarge.boundingBox.center.x) < 0.05 },
                          "the largest blob must be served every cycle (cycle \(cycle))")
        }
    }

    func testRotationServesTheOtherBlobsWithinTheRestCount() {
        var config = SchedulerConfig()
        config.maxMotionCrops = 2
        let scheduler = Scheduler(config: config)
        let blobs = [rotationSmall, rotationMedium, rotationLarge]

        // Two non-largest blobs share one rotating slot, so two cycles are guaranteed to
        // visit both: this is the exact bound the rotation offers here, not a margin.
        var sawMedium = false
        var sawSmall = false
        for _ in 0..<2 {
            let centres = motionCentres(scheduler.next(blobs: blobs))
            if centres.contains(where: { abs($0 - rotationMedium.boundingBox.center.x) < 0.05 }) {
                sawMedium = true
            }
            if centres.contains(where: { abs($0 - rotationSmall.boundingBox.center.x) < 0.05 }) {
                sawSmall = true
            }
        }
        XCTAssertTrue(sawMedium, "the medium blob must be served within the rotation window")
        XCTAssertTrue(sawSmall, "the small blob must be served within the rotation window")
    }

    func testRotationServesEveryNonLargestBlobWithinFourCycles() {
        var config = SchedulerConfig()
        config.maxMotionCrops = 2
        let scheduler = Scheduler(config: config)

        let blobs = [
            Blob(boundingBox: Rect(x: 0.2, y: 0.5, width: 0.03, height: 0.03), area: 10),
            Blob(boundingBox: Rect(x: 0.35, y: 0.5, width: 0.03, height: 0.03), area: 20),
            Blob(boundingBox: Rect(x: 0.5, y: 0.5, width: 0.03, height: 0.03), area: 30),
            Blob(boundingBox: Rect(x: 0.65, y: 0.5, width: 0.03, height: 0.03), area: 40),
            Blob(boundingBox: Rect(x: 0.8, y: 0.5, width: 0.03, height: 0.03), area: 100),
        ]
        let largest = blobs[4]
        let others = Array(blobs.prefix(4))

        var servedOthers = Set<Int>()
        for cycle in 0..<4 {
            let centres = motionCentres(scheduler.next(blobs: blobs))
            XCTAssertTrue(centres.contains { abs($0 - largest.boundingBox.center.x) < 0.05 },
                          "the largest blob must be served every cycle (cycle \(cycle))")
            for (index, other) in others.enumerated() {
                if centres.contains(where: { abs($0 - other.boundingBox.center.x) < 0.05 }) {
                    servedOthers.insert(index)
                }
            }
        }
        XCTAssertEqual(servedOthers.count, others.count,
                       "every non-largest blob must be served at least once within four cycles")
    }

    func testASingleBlobIsServedEveryCycle() {
        let scheduler = Scheduler()   // default maxMotionCrops = 2, but only one blob exists
        let only = Blob(boundingBox: Rect(x: 0.5, y: 0.5, width: 0.05, height: 0.05), area: 50)

        for _ in 0..<3 {
            let crops = scheduler.next(blobs: [only]).filter { $0.kind == .motion }
            XCTAssertEqual(crops.count, 1)
            XCTAssertEqual(crops[0].rect.center.x, only.boundingBox.center.x, accuracy: 1e-6)
        }
    }
}
