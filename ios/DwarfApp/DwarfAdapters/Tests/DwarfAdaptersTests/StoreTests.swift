import XCTest
import DwarfCore
@testable import DwarfAdapters

final class StoreTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testAFreshStoreIsUsableAndSaysItIsUncalibrated() {
        let store = Store(directory: directory)
        XCTAssertEqual(store.settings.mode, .dryRun, "a gnome that has never been told otherwise does not fire")
        XCTAssertTrue(store.calibration.points.isEmpty)
        XCTAssertFalse(store.isCalibrated)
    }

    func testSettingsSurviveARestart() throws {
        let store = Store(directory: directory)
        store.settings.mode = .live
        store.settings.quarterTurns = 1
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .live)
        XCTAssertEqual(reopened.settings.quarterTurns, 1)
    }

    func testACalibrationSurvivesARestart() throws {
        let store = Store(directory: directory)
        store.calibration = Calibration(
            points: (0..<6).map {
                CalibrationPoint(image: Point(x: 0.1 * Double($0), y: 0.6),
                                 pan: Double($0), tilt: 1, rangeM: 4)
            },
            heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4)])
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.calibration.points.count, 6)
        XCTAssertTrue(reopened.isCalibrated)
    }

    func testATruncatedFileFallsBackRatherThanRefusingToStart() throws {
        // A power cut during a write is the normal way this happens, and a gnome that will
        // not boot in the garden is worse than one that boots uncalibrated and says so.
        let store = Store(directory: directory)
        store.settings.mode = .live
        try store.save()

        try Data("{ \"mode\": ".utf8).write(to: directory.appendingPathComponent("settings.json"))

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .dryRun)
        XCTAssertEqual(reopened.loadFailures, ["settings.json"])
    }

    func testAWriteIsAtomic() throws {
        // Written to a neighbouring file and moved into place, so the file at the real path
        // is always either the old one or the new one and never half of either.
        let store = Store(directory: directory)
        store.settings.mode = .live
        try store.save()
        try store.save()

        let leftovers = try FileManager.default.contentsOfDirectory(atPath: directory.path)
            .filter { $0.hasSuffix(".tmp") }
        XCTAssertTrue(leftovers.isEmpty, "temporary files left behind: \(leftovers)")
    }

    func testMasksRoundTrip() throws {
        let store = Store(directory: directory)
        store.masks = MaskSet(
            ignoreZones: [Polygon(points: [Point(x: 0, y: 0), Point(x: 0.2, y: 0), Point(x: 0.2, y: 0.2)])],
            noFireZones: [Polygon(points: [Point(x: 0.8, y: 0.8), Point(x: 1, y: 0.8), Point(x: 1, y: 1)])])
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.masks.ignoreZones.count, 1)
        XCTAssertEqual(reopened.masks.noFireZones.count, 1)
        XCTAssertEqual(reopened.masks.noFireMargin, 0.005, accuracy: 1e-12,
                       "the safety margin must survive a round trip too")
    }

    func testAFormatFromTheFutureIsNotGuessedAt() throws {
        // A phone running an old build against files written by a new one should say so
        // rather than misread them.
        let store = Store(directory: directory)
        try store.save()
        let path = directory.appendingPathComponent("settings.json")
        var object = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
        object["formatVersion"] = DwarfAdapters.formatVersion + 1
        try JSONSerialization.data(withJSONObject: object).write(to: path)

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .dryRun)
        XCTAssertEqual(reopened.loadFailures, ["settings.json"])
    }
}
