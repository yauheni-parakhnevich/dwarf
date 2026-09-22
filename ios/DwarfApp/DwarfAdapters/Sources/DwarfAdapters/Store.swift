import Foundation
import DwarfCore

/// Everything the owner can change that is not a calibration or a mask.
public struct Settings: Codable, Equatable, Sendable {
    /// Persisted across restarts, as the spec requires. A gnome left in `live` comes back
    /// in `live`.
    public var mode: Mode = .dryRun
    /// Quarter turns clockwise to stand the camera buffer upright; see `FrameGeometry`.
    public var quarterTurns = 0
    /// The model's input side. M0 decides this: measured on the gnome's own iPhone 6s on
    /// 2026-09-22, YOLO11n at 640 sustained 3.33 inferences a second for ten minutes
    /// without the phone leaving nominal thermal state, so 640 stays and the fallbacks to
    /// 416 and 320 are not needed.
    public var modelSide = 640
    public var minConfidence = 0.25
    /// Seconds one inference takes on this phone, from M0. The tracker counts its windows
    /// in detector answers rather than in frames, so this is what they have to be sized
    /// against; see `Runtime`.
    public var detectorLatency = 0.30

    public init() {}
}

/// What every file on disk is wrapped in.
///
/// The version used to sit inside `Settings` alone, which left calibrations and masks with
/// no way to say which build wrote them. A future change that stays type-compatible — a
/// range recorded in centimetres where it used to be metres, say — would decode perfectly
/// and be silently a hundred times wrong, with nothing in `loadFailures` to show for it.
/// A wrapper costs one line per file and closes that for all three.
private struct Versioned<Value: Codable>: Codable {
    var formatVersion: Int
    var value: Value
}

/// Mode, calibration and masks on disk.
///
/// Reading is forgiving and writing is atomic. A file that will not parse is reported and
/// replaced with a default, because a gnome that refuses to start in the garden is worse
/// than one that starts uncalibrated and says so on its screen — and an uncalibrated gnome
/// cannot fire at all, so failing this way is safe as well as convenient.
public final class Store {
    public var settings: Settings
    public var calibration: Calibration {
        didSet { isCalibrated = Store.canAim(calibration) }
    }
    public var masks: MaskSet

    /// Files that could not be read this launch, for the status screen.
    public private(set) var loadFailures: [String] = []

    /// Whether this calibration can actually produce an aim, which is not the same as
    /// having enough points. `Aimer` needs six, and it needs them not to be degenerate:
    /// six points along a single line satisfy the count and leave the fit singular, so a
    /// naive `points.count >= 6` reported a calibrated gnome that could never aim. An owner
    /// walking one straight path while recording is a realistic way to produce exactly
    /// that. Asking `Aimer` is the only answer that cannot drift from the truth.
    public private(set) var isCalibrated: Bool

    private let directory: URL

    public init(directory: URL) {
        self.directory = directory

        var failures: [String] = []
        func load<T: Codable>(_ name: String, _ fallback: T) -> T {
            let url = directory.appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath: url.path) else { return fallback }
            do {
                let wrapper = try JSONDecoder().decode(Versioned<T>.self, from: Data(contentsOf: url))
                guard wrapper.formatVersion <= DwarfAdapters.formatVersion else {
                    // Written by a newer build. Guessing at a shape this one does not
                    // understand is how a no-fire zone silently goes missing.
                    failures.append(name)
                    return fallback
                }
                return wrapper.value
            } catch {
                failures.append(name)
                return fallback
            }
        }

        self.settings = load("settings.json", Settings())
        let calibration: Calibration = load("calibration.json", .empty)
        self.calibration = calibration
        self.isCalibrated = Store.canAim(calibration)
        self.masks = load("masks.json", .empty)
        self.loadFailures = failures
    }

    /// Encodes all three, then swaps all three into place.
    ///
    /// Each file lands atomically, but the three together do not, and they are related:
    /// losing power between the calibration and the masks leaves a gnome aiming with one
    /// and excluding with the other's predecessor, both files individually valid and
    /// nothing in `loadFailures` to say so. Writing every temporary file before renaming
    /// any of them shrinks that window from three encode-and-writes to three renames.
    public func save() throws {
        let pending: [(name: String, data: Data)] = [
            ("settings.json", try encode(settings)),
            ("calibration.json", try encode(calibration)),
            ("masks.json", try encode(masks))
        ]

        for file in pending {
            try file.data.write(to: temporaryURL(file.name), options: .atomic)
        }
        for file in pending {
            _ = try FileManager.default.replaceItemAt(url(file.name),
                                                      withItemAt: temporaryURL(file.name))
        }
    }

    private static func canAim(_ calibration: Calibration) -> Bool {
        Aimer(calibration: calibration) != nil
    }

    private func encode<T: Encodable & Decodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(Versioned(formatVersion: DwarfAdapters.formatVersion,
                                            value: value))
    }

    private func url(_ name: String) -> URL { directory.appendingPathComponent(name) }
    private func temporaryURL(_ name: String) -> URL { url(name + ".tmp") }
}
