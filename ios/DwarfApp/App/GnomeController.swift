import Foundation
import SwiftUI
import DwarfCore
import DwarfAdapters

/// Assembles the gnome and publishes enough of it for the screen.
///
/// Deliberately **not** `@MainActor`: camera frames arrive on the capture queue and go
/// straight into the runtime from there, so isolating this type to the main actor would
/// either block the UI or need every frame to hop threads. Only the published properties
/// touch the main actor, and they do it explicitly.
final class GnomeController: ObservableObject {
    @Published private(set) var line = "starting"
    @Published private(set) var trackCount = 0
    @Published private(set) var linkUp = false
    @Published private(set) var mode: Mode = .dryRun
    /// Counters that should normally read empty. Anything here means the gnome is running
    /// but not doing what it looks like it is doing.
    @Published private(set) var health = ""
    /// True when the model could not be loaded. The gnome then tracks nothing at all, and
    /// silently looking like it works is the worst way for that to present.
    @Published private(set) var modelMissing = false

    private let camera = CameraSource()
    private let runtime: Runtime
    private let store: Store
    private let link: ActuatorLink

    init() {
        let directory = FileManager.default.urls(for: .applicationSupportDirectory,
                                                 in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let store = Store(directory: directory)
        let clock = SteadyClock(wrapping: SystemClock())
        // TODO(Task 9): swap for BluetoothTransport once the firmware side (Task 11) and
        // the CoreBluetooth transport (Task 9) exist. Neither has been written yet, so this
        // stands in for it: FakeTransport never reports connected, which means the app
        // builds and the whole screen runs against a link that simply never comes up
        // (linkUp stays false, status(asOf:) always returns nil, sends fail and count in
        // sendFailures) rather than pretending to talk to a gnome that isn't there.
        let transport = FakeTransport()
        let link = ActuatorLink(transport: transport, clock: clock)
        // A missing or unreadable model must be visible, not papered over: the fallback
        // detector never finds anything, so the gnome would sit there looking healthy and
        // watching nothing.
        let detector: Detector
        var missing = false
        if let model = try? CoreMLDetector(minConfidence: store.settings.minConfidence) {
            detector = model
        } else {
            detector = FakeDetector()
            missing = true
        }

        self.store = store
        self.link = link
        self.runtime = Runtime(
            store: store,
            link: link,
            detector: detector,
            geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                    quarterTurns: store.settings.quarterTurns),
            power: PowerManager(battery: DeviceBattery()),
            clock: clock)
        self.mode = store.settings.mode
        self.modelMissing = missing
    }

    func start() {
        camera.onFrame = { [weak self] buffer in
            guard let self else { return }
            self.runtime.handle(frame: buffer)
            Task { @MainActor in self.refresh() }
        }
        do {
            try camera.start()
            line = "watching"
        } catch {
            line = "no camera: \(error)"
        }
    }

    func set(mode: Mode) {
        self.mode = mode
        runtime.update(mode: mode)
        try? store.save()
    }

    private func refresh() {
        let snapshot = runtime.snapshot
        linkUp = link.isConnected
        trackCount = snapshot.tracks.count

        // Everything the review of Task 12 added a counter for, surfaced. A gnome that has
        // quietly stopped working should say so on its own screen rather than be diagnosed
        // from a crash report.
        //
        // `RuntimeSnapshot` has no `lumaUnusable` field of its own — that flag lives on
        // `PowerDecision`, which `Runtime` consumes and does not carry into the snapshot —
        // so it is recomputed here from the same test `PowerManager` uses (`!meanLuma.isFinite`)
        // against the snapshot's own `meanLuma`, rather than adding a field to Task 12's
        // already-reviewed `RuntimeSnapshot`.
        health = [
            snapshot.droppedRequests > 0 ? "dropped \(snapshot.droppedRequests)" : nil,
            snapshot.sendFailures > 0 ? "send fails \(snapshot.sendFailures)" : nil,
            snapshot.detectorFailures > 0 ? "model fails \(snapshot.detectorFailures)" : nil,
            !snapshot.meanLuma.isFinite ? "luma unusable" : nil
        ].compactMap { $0 }.joined(separator: " · ")

        if modelMissing {
            line = "MODEL MISSING — nothing is being detected"
        } else if !store.loadFailures.isEmpty {
            line = "unreadable: \(store.loadFailures.joined(separator: ", "))"
        } else if !store.isCalibrated {
            line = "tracking only — not calibrated"
        } else {
            line = describe(snapshot.decision)
        }
    }

    private func describe(_ decision: FireDecision) -> String {
        switch decision {
        case .none: return "watching"
        case .aim(let pan, let tilt): return String(format: "aim %.1f° %.1f°", pan, tilt)
        case .park: return "parked"
        case .shoot(_, _, let ms): return "SHOT \(ms) ms"
        case .wouldShoot(_, _, let ms): return "would shoot \(ms) ms"
        }
    }
}
