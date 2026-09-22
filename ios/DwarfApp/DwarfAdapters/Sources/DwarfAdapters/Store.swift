import Foundation
import DwarfCore

/// Everything the owner can change that is not a calibration or a mask.
public struct Settings: Codable, Equatable, Sendable {
    public var formatVersion = DwarfAdapters.formatVersion
    /// Persisted across restarts, as the spec requires. A gnome left in `live` comes back
    /// in `live`.
    public var mode: Mode = .dryRun
    /// Quarter turns clockwise to stand the camera buffer upright; see `FrameGeometry`.
    public var quarterTurns = 0
    /// The model's input side. M0 decides this.
    public var modelSide = 640
    public var minConfidence = 0.25

    public init() {}
}

/// Mode, calibration and masks on disk.
///
/// Reading is forgiving and writing is atomic. A file that will not parse is reported and
/// replaced with a default, because a gnome that refuses to start in the garden is worse
/// than one that starts uncalibrated and says so on its screen — and an uncalibrated gnome
/// cannot fire at all, so failing this way is safe as well as convenient.
public final class Store {
    public var settings: Settings
    public var calibration: Calibration
    public var masks: MaskSet

    /// Files that could not be read this launch, for the status screen.
    public private(set) var loadFailures: [String] = []

    /// True when there is enough calibration for `Aimer` to fit at all. Below this the
    /// gnome tracks and shows a live view but has no route to a shot.
    public var isCalibrated: Bool { calibration.points.count >= 6 }

    private let directory: URL

    public init(directory: URL) {
        self.directory = directory

        var failures: [String] = []
        func load<T: Decodable>(_ name: String, _ fallback: T) -> T {
            let url = directory.appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath: url.path) else { return fallback }
            do {
                return try JSONDecoder().decode(T.self, from: Data(contentsOf: url))
            } catch {
                failures.append(name)
                return fallback
            }
        }

        var loaded: Settings = load("settings.json", Settings())
        if loaded.formatVersion > DwarfAdapters.formatVersion {
            // Written by a newer build. Guessing at fields this one does not understand is
            // how a setting silently reverts.
            failures.append("settings.json")
            loaded = Settings()
        }
        self.settings = loaded
        self.calibration = load("calibration.json", .empty)
        self.masks = load("masks.json", .empty)
        self.loadFailures = failures
    }

    public func save() throws {
        settings.formatVersion = DwarfAdapters.formatVersion
        try write(settings, to: "settings.json")
        try write(calibration, to: "calibration.json")
        try write(masks, to: "masks.json")
    }

    /// Written beside the real file and moved into place, so a power cut mid-write leaves
    /// the previous version rather than half of the new one.
    private func write<T: Encodable>(_ value: T, to name: String) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(value)

        let target = directory.appendingPathComponent(name)
        let temporary = directory.appendingPathComponent(name + ".tmp")
        try data.write(to: temporary, options: .atomic)
        _ = try FileManager.default.replaceItemAt(target, withItemAt: temporary)
    }
}
