import Foundation
import SwiftUI
import DwarfCore
import DwarfAdapters

/// Assembles the gnome and publishes enough of it to diagnose one.
///
/// Deliberately **not** `@MainActor`: camera frames arrive on the capture queue and go
/// straight into the runtime from there, so isolating this type to the main actor would
/// either block the UI or make every frame hop threads. Only the published properties touch
/// the main actor, and they do it explicitly. This project has already lost a day to
/// `SwiftUI.View` being main-actor-isolated and quietly pulling ten minutes of CoreML onto
/// the main thread; nothing here is allowed to be vague about which queue it runs on.
final class GnomeController: ObservableObject {
    @Published private(set) var snapshot = RuntimeSnapshot()
    @Published private(set) var linkUp = false
    /// True while the gnome is in range but refusing every command for want of a bond — a
    /// different instruction to the owner than "no link". See `BluetoothTransport`.
    @Published private(set) var needsPairing = false
    @Published private(set) var mode: Mode = .dryRun
    @Published private(set) var camera: CameraSource.Health = .stopped
    @Published private(set) var modelMissing = false
    @Published private(set) var loadFailures: [String] = []
    @Published private(set) var calibrated = false
    @Published private(set) var calibrationPoints = 0
    @Published private(set) var noFireZones = 0
    @Published private(set) var frameRate: Double = 0

    private let source = CameraSource()
    private let store: Store
    private let link: ActuatorLink
    /// Kept alongside `link` (which only sees it through the `Transport` protocol) so
    /// `needsPairing` — not part of that protocol, since nothing else the app talks to over
    /// it needs bonding — can be read for the UI.
    private let transport: BluetoothTransport
    private var runtime: Runtime?
    /// Building the runtime loads and compiles the CoreML model, which is real blocking
    /// work. It happens on this queue, not on the main actor during a first `body`.
    private let setup = DispatchQueue(label: "garden.dwarf.setup")
    /// One refresh in flight at a time. Frames arrive ten times a second and the main actor
    /// has no equivalent of the detector's busy flag, so unstructured tasks would otherwise
    /// pile up uncapped the moment the main thread fell behind.
    private let refreshing = NSLock()
    private var refreshQueued = false

    init() {
        let directory = FileManager.default.urls(for: .applicationSupportDirectory,
                                                 in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let store = Store(directory: directory)
        let clock = SteadyClock(wrapping: SystemClock())
        // The real radio. CoreBluetooth behind `Transport`; see `BluetoothTransport` for why
        // it is thin and where the pairing-state logic it drives actually lives.
        let transport = BluetoothTransport()

        self.store = store
        self.transport = transport
        self.link = ActuatorLink(transport: transport, clock: clock)
        self.mode = store.settings.mode
        self.loadFailures = store.loadFailures
        self.calibrated = store.isCalibrated
        self.calibrationPoints = store.calibration.points.count
        self.noFireZones = store.masks.noFireZones.count

        setup.async { [weak self] in
            guard let self else { return }
            // A missing model must be visible, not papered over: the fallback detector never
            // finds anything, so the gnome would sit there looking healthy and watching
            // nothing.
            let detector: Detector
            var missing = false
            if let model = try? CoreMLDetector(minConfidence: store.settings.minConfidence) {
                detector = model
            } else {
                detector = FakeDetector()
                missing = true
            }

            let runtime = Runtime(
                store: store,
                link: self.link,
                detector: detector,
                geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                        quarterTurns: store.settings.quarterTurns),
                power: PowerManager(battery: DeviceBattery()),
                clock: clock)
            self.runtime = runtime
            DispatchQueue.main.async { self.modelMissing = missing }
        }
    }

    func start() {
        source.onHealthChange = { [weak self] health in self?.camera = health }
        source.onFrame = { [weak self] buffer in
            // Capture queue. Everything in handle(frame:) runs here, except the CoreML call,
            // which Runtime puts on its own queue.
            guard let self, let runtime = self.runtime else { return }
            runtime.handle(frame: buffer)
            self.scheduleRefresh()
        }
        source.start()
    }

    func set(mode: Mode) {
        self.mode = mode
        // Queued, and persisted by the runtime once it has actually landed. Saving from
        // here would read Store from the main actor while the capture queue writes it, and
        // would write the previous mode to disk.
        runtime?.update(mode: mode)
    }

    private func scheduleRefresh() {
        refreshing.lock()
        let alreadyQueued = refreshQueued
        refreshQueued = true
        refreshing.unlock()
        guard !alreadyQueued else { return }

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.refreshing.lock()
            self.refreshQueued = false
            self.refreshing.unlock()

            self.snapshot = self.runtime?.snapshot ?? RuntimeSnapshot()
            self.linkUp = self.link.isConnected
            self.needsPairing = self.transport.needsPairing
            self.frameRate = self.source.actualFrameRate
        }
    }
}
