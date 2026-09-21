import XCTest
@testable import DwarfCore

final class TrackingTests: XCTestCase {
    private func detection(x: Double, y: Double, confidence: Double = 0.9) -> Detection {
        Detection(box: Rect(x: x, y: y, width: 0.08, height: 0.06), confidence: confidence)
    }

    func testFirstDetectionCreatesAnUnconfirmedTrack() {
        let tracker = Tracker()
        let tracks = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertFalse(tracks[0].isConfirmed, "one look is never enough to fire")
    }

    func testTwoOfThreeLooksConfirms() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.505, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertTrue(tracks[0].isConfirmed)
    }

    func testLowConfidenceDetectionsDoNotConfirm() {
        var config = TrackerConfig()
        config.minConfidence = 0.5
        let tracker = Tracker(config: config)

        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5, confidence: 0.3)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.5, y: 0.5, confidence: 0.35)], at: 0.1)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertFalse(tracks[0].isConfirmed)
    }

    func testAMissedLookCountsAgainstConfirmation() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        _ = tracker.update(detections: [], at: 0.1)
        let tracks = tracker.update(detections: [], at: 0.2)

        XCTAssertEqual(tracks.count, 1, "the track survives briefly so it can be re-acquired")
        XCTAssertFalse(tracks[0].isConfirmed, "one hit in the last three looks is not enough")
    }

    func testNearbyDetectionsAssociateToTheSameTrack() {
        let tracker = Tracker()
        let first = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        let second = tracker.update(detections: [detection(x: 0.51, y: 0.5)], at: 0.1)

        XCTAssertEqual(first[0].id, second[0].id)
    }

    func testADistantDetectionStartsANewTrack() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.2, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.8, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 2)
        XCTAssertNotEqual(tracks[0].id, tracks[1].id)
    }

    func testTwoCatsKeepSeparateIdentities() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.2, y: 0.5), detection(x: 0.8, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.21, y: 0.5), detection(x: 0.79, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 2)
        XCTAssertEqual(Set(tracks.map(\.id)).count, 2)
    }

    func testAStationaryTrackIsStill() {
        let tracker = Tracker()
        var time = 0.0
        for _ in 0..<12 {
            _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: time)
            time += 0.1
        }
        XCTAssertTrue(tracker.tracks[0].isStill)
    }

    func testAWalkingTrackIsNotStill() {
        let tracker = Tracker()
        var time = 0.0
        var x = 0.2
        for _ in 0..<12 {
            _ = tracker.update(detections: [detection(x: x, y: 0.5)], at: time)
            time += 0.1
            x += 0.02   // 0.2 frame widths per second, well above the threshold
        }
        XCTAssertFalse(tracker.tracks[0].isStill)
    }

    func testANewTrackIsNotYetStill() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        XCTAssertFalse(tracker.tracks[0].isStill,
                       "stillness needs a full window of history, not one sample")
    }

    func testTracksAreDroppedAfterGoingUnseen() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        _ = tracker.update(detections: [], at: 1.0)
        XCTAssertEqual(tracker.tracks.count, 1)

        let tracks = tracker.update(detections: [], at: 3.5)
        XCTAssertTrue(tracks.isEmpty)
    }

    func testGroundPointIsTheBottomOfTheBox() {
        let tracker = Tracker()
        let tracks = tracker.update(detections: [detection(x: 0.4, y: 0.3)], at: 0)
        XCTAssertEqual(tracks[0].groundPoint.y, 0.36, accuracy: 1e-9)
        XCTAssertEqual(tracks[0].groundPoint.x, 0.44, accuracy: 1e-9)
    }

    // MARK: - Robustness fixes: pacing, duplicate looks, crossings, frame rate

    func testAPacingTrackIsNotStill() {
        let tracker = Tracker()
        var time = 0.0
        // Ends back near where it started, but has covered real ground getting there:
        // the endpoint measure would miss this entirely.
        let xs: [Double] = [0.5, 0.54, 0.58, 0.62, 0.66, 0.70, 0.66, 0.62, 0.58, 0.54, 0.50]
        for x in xs {
            _ = tracker.update(detections: [detection(x: x, y: 0.5)], at: time)
            time += 0.1
        }
        XCTAssertFalse(tracker.tracks[0].isStill, "endpoints match, but the animal paced the whole window")
    }

    func testTwoCallsAtTheSameTimestampCountAsOneLook() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        // A second crop of the same cat processed within the same scheduler cycle: same
        // timestamp, not a new moment.
        let tracks = tracker.update(detections: [detection(x: 0.505, y: 0.5)], at: 0)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertFalse(tracks[0].isConfirmed, "two crops of one moment must not count as two independent looks")
    }

    func testOverlappingDetectionsInOneCallProduceOneTrack() {
        let tracker = Tracker()
        // Two crops covering the same physical cat this cycle: nearly identical boxes,
        // both handed to a single update() call.
        let tracks = tracker.update(
            detections: [detection(x: 0.5, y: 0.5), detection(x: 0.505, y: 0.5)],
            at: 0
        )

        XCTAssertEqual(tracks.count, 1, "overlapping crops of one cat must not double its shot budget later")
    }

    func testCloseTracksAreFlaggedAmbiguous() {
        let tracker = Tracker()
        // 0.08 apart: farther than the 0.05 gate (so two distinct tracks), but within
        // ambiguityFactor(2.0) * gate = 0.10 (so both are flagged).
        let tracks = tracker.update(
            detections: [detection(x: 0.5, y: 0.5), detection(x: 0.58, y: 0.5)],
            at: 0
        )

        XCTAssertEqual(tracks.count, 2, "far enough apart to be distinct tracks")
        XCTAssertTrue(tracks[0].isAmbiguous)
        XCTAssertTrue(tracks[1].isAmbiguous)
    }

    func testWellSeparatedTracksAreNotAmbiguous() {
        let tracker = Tracker()
        let tracks = tracker.update(
            detections: [detection(x: 0.2, y: 0.5), detection(x: 0.8, y: 0.5)],
            at: 0
        )

        XCTAssertEqual(tracks.count, 2)
        XCTAssertFalse(tracks[0].isAmbiguous)
        XCTAssertFalse(tracks[1].isAmbiguous)
    }

    func testAWalkingTrackAt3FpsKeepsOneID() {
        let tracker = Tracker()
        var time = 0.0
        var x = 0.1
        var ids = Set<Int>()
        let dt = 0.333   // ~3 fps
        while x < 0.8 {
            let tracks = tracker.update(detections: [detection(x: x, y: 0.5)], at: time)
            ids.formUnion(tracks.map(\.id))
            time += dt
            x += 0.25 * dt   // 0.25 frame widths per second: a plausible walking cat
        }
        XCTAssertEqual(ids.count, 1, "a fixed gate would have fragmented this into a new track almost every frame")
    }
}
