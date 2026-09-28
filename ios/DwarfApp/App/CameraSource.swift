import Foundation
import AVFoundation
import CoreVideo

/// 1080p frames at roughly 10 fps, in the camera's native format.
///
/// `420YpCbCr8BiPlanarFullRange` is what the sensor produces, so nothing is converted at
/// capture time and `FrameConverter` gets the luma plane for free. 1080p rather than 4K: at
/// 6 m a cat is about 75 px long here, which is enough, and four times the pixels would cost
/// four times the heat for no more reach.
public final class CameraSource: NSObject {
    public enum Health: Equatable {
        case stopped
        case running
        /// iOS took the camera away: a phone call, another app, the screen locking.
        case interrupted(String)
        case failed(String)
        case denied
    }

    public var onFrame: ((CVPixelBuffer) -> Void)?
    /// Called on the main queue whenever the session's health changes. A camera that has
    /// silently stopped is indistinguishable from an empty garden, which is the worst way
    /// for this to fail.
    public var onHealthChange: ((Health) -> Void)?
    /// The frame duration the device actually accepted, which is not always the one asked
    /// for: assigning a duration outside the active format's supported range is clamped
    /// silently rather than refused.
    public private(set) var actualFrameRate: Double = 0

    /// Exposed so a preview layer can show what the pipeline is actually looking at.
    /// Read-only by convention: configuration belongs to `configure()`, on the control
    /// queue, and a preview layer only ever reads frames the session is already producing.
    public let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let frames = DispatchQueue(label: "garden.dwarf.capture")
    /// Configuration and start/stop, off the main thread. `startRunning()` blocks, and
    /// Apple's own guidance is to keep it off the main queue for exactly that reason.
    private let control = DispatchQueue(label: "garden.dwarf.capture.control")

    public override init() {
        super.init()
        let centre = NotificationCenter.default
        centre.addObserver(self, selector: #selector(runtimeError(_:)),
                           name: .AVCaptureSessionRuntimeError, object: session)
        centre.addObserver(self, selector: #selector(interrupted(_:)),
                           name: .AVCaptureSessionWasInterrupted, object: session)
        centre.addObserver(self, selector: #selector(interruptionEnded(_:)),
                           name: .AVCaptureSessionInterruptionEnded, object: session)
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    /// Returns immediately; the outcome arrives through `onHealthChange`.
    public func start() {
        control.async { [weak self] in
            guard let self else { return }

            switch AVCaptureDevice.authorizationStatus(for: .video) {
            case .authorized:
                break
            case .notDetermined:
                let semaphore = DispatchSemaphore(value: 0)
                var granted = false
                AVCaptureDevice.requestAccess(for: .video) { granted = $0; semaphore.signal() }
                semaphore.wait()
                guard granted else { return self.report(.denied) }
            default:
                return self.report(.denied)
            }

            do {
                try self.configure()
            } catch {
                return self.report(.failed("\(error)"))
            }
            self.session.startRunning()
            self.report(self.session.isRunning ? .running : .failed("session did not start"))
        }
    }

    public func stop() {
        control.async { [weak self] in
            self?.session.stopRunning()
            self?.report(.stopped)
        }
    }

    private func configure() throws {
        session.beginConfiguration()
        // Committed on every path out, including the throwing ones: leaving a configuration
        // transaction open makes the next attempt's behaviour undefined.
        defer { session.commitConfiguration() }

        session.sessionPreset = .hd1920x1080

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            throw CameraError.noCamera
        }
        session.addInput(input)

        output.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String:
                kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
        ]
        // Frames are dropped rather than queued. A backlog would hand the runtime pictures
        // of where the cat used to be.
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: frames)
        guard session.canAddOutput(output) else { throw CameraError.noCamera }
        session.addOutput(output)

        try device.lockForConfiguration()
        defer { device.unlockForConfiguration() }
        // Ask for 10 fps at both ends, so the sensor is not working harder than the pipeline
        // can consume. On an A9 every unused frame is heat.
        device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 10)
        device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 10)
        // Read back rather than assume: a duration outside the active format's supported
        // range is clamped without complaint, so "10 fps" can quietly be 24.
        let accepted = device.activeVideoMinFrameDuration
        actualFrameRate = accepted.value > 0 ? Double(accepted.timescale) / Double(accepted.value) : 0

        // The gnome does not move and the garden does not change distance. Continuous
        // autofocus hunting through a plastic window is worse than a fixed far focus.
        if device.isFocusModeSupported(.continuousAutoFocus) {
            device.focusMode = .continuousAutoFocus
        }
    }

    private func report(_ health: Health) {
        DispatchQueue.main.async { [weak self] in self?.onHealthChange?(health) }
    }

    @objc private func runtimeError(_ note: Notification) {
        let error = note.userInfo?[AVCaptureSessionErrorKey] as? NSError
        report(.failed(error?.localizedDescription ?? "runtime error"))
        // A media-services reset is recoverable, and the gnome is unattended.
        control.asyncAfter(deadline: .now() + 2) { [weak self] in
            guard let self, !self.session.isRunning else { return }
            self.session.startRunning()
            self.report(self.session.isRunning ? .running : .failed("could not restart"))
        }
    }

    @objc private func interrupted(_ note: Notification) {
        let raw = note.userInfo?[AVCaptureSessionInterruptionReasonKey] as? Int
        report(.interrupted(raw.map(String.init) ?? "unknown"))
    }

    @objc private func interruptionEnded(_ note: Notification) {
        report(session.isRunning ? .running : .stopped)
    }

    public enum CameraError: Error { case noCamera }
}

extension CameraSource: AVCaptureVideoDataOutputSampleBufferDelegate {
    public func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                              from connection: AVCaptureConnection) {
        guard let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        onFrame?(buffer)
    }
}
