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

    /// A calibration the Aimer can actually fit: a quadratic surface has six coefficients
    /// including y squared, so the samples need at least three distinct rows as well as
    /// three distinct columns. Two rows leave y and y squared linearly dependent and the
    /// fit singular, however many points sit in them.
    private func usableCalibration() -> Calibration {
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                points.append(CalibrationPoint(image: Point(x: x, y: y),
                                               pan: (x - 0.5) * 100,
                                               tilt: 30 - 34 * y,
                                               rangeM: 8 - 6 * y))
            }
        }
        return Calibration(points: points,
                           heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4)])
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
        // Spread over two rows, not one: six points along a single line satisfy the count
        // and leave the fit singular, which is what testSixCollinearPointsAreNotACalibration
        // is about.
        store.calibration = usableCalibration()
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.calibration.points.count, usableCalibration().points.count)
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

    func testSixCollinearPointsAreNotACalibration() {
        // Enough points, and useless: six samples along one line leave the quadratic fit
        // singular, so Aimer refuses to build. Counting points reported a calibrated gnome
        // that could never aim, and an owner walking one straight path while recording is
        // a realistic way to produce exactly that.
        let store = Store(directory: directory)
        store.calibration = Calibration(
            points: (0..<6).map {
                CalibrationPoint(image: Point(x: 0.1 * Double($0) + 0.1, y: 0.5),
                                 pan: Double($0) * 10, tilt: 5, rangeM: 4)
            },
            heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4)])

        XCTAssertEqual(store.calibration.points.count, 6)
        XCTAssertNil(Aimer(calibration: store.calibration), "the fit really is singular")
        XCTAssertFalse(store.isCalibrated, "so the gnome must not claim it is calibrated")
    }

    func testAUsableCalibrationIsRecognised() {
        let store = Store(directory: directory)
        store.calibration = usableCalibration()
        XCTAssertTrue(store.isCalibrated)
    }

    func testAFutureFormatIsRefusedForEveryFileNotJustSettings() throws {
        // Calibrations and masks carry a version now too. A range recorded in centimetres
        // where it used to be metres would decode perfectly and be a hundred times wrong.
        let store = Store(directory: directory)
        try store.save()

        for name in ["calibration.json", "masks.json"] {
            let path = directory.appendingPathComponent(name)
            var object = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
            object["formatVersion"] = DwarfAdapters.formatVersion + 1
            try JSONSerialization.data(withJSONObject: object).write(to: path)
        }

        let reopened = Store(directory: directory)
        XCTAssertEqual(Set(reopened.loadFailures), ["calibration.json", "masks.json"])
        XCTAssertTrue(reopened.calibration.points.isEmpty)
    }
}
