import Foundation
import AVFoundation
import CoreVideo

/// 1080p frames at roughly 10 fps, in the camera's native format.
///
/// `420YpCbCr8BiPlanarFullRange` is what the sensor produces, so nothing is converted at
/// capture time and `FrameConverter` gets the luma plane for free. 1080p rather than 4K:
/// at 6 m a cat is about 75 px long here, which is enough, and four times the pixels would
/// cost four times the heat for no more reach.
public final class CameraSource: NSObject {
    public var onFrame: ((CVPixelBuffer) -> Void)?

    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "garden.dwarf.capture")

    public func start() throws {
        session.beginConfiguration()
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
        output.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(output) else { throw CameraError.noCamera }
        session.addOutput(output)

        try device.lockForConfiguration()
        // Ask for 10 fps at both ends, so the sensor is not working harder than the pipeline
        // can consume. On an A9 every unused frame is heat.
        device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 10)
        device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 10)
        // The gnome does not move and the garden does not change distance. Continuous
        // autofocus hunting through a plastic window is worse than a fixed far focus.
        if device.isFocusModeSupported(.continuousAutoFocus) {
            device.focusMode = .continuousAutoFocus
        }
        device.unlockForConfiguration()

        session.commitConfiguration()
        session.startRunning()
    }

    public func stop() {
        session.stopRunning()
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
