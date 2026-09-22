import SwiftUI
import AVFoundation

/// The camera's own frames, behind the overlay.
///
/// Worth the small GPU cost: the boxes alone tell you something was detected, not whether
/// the gnome is looking where you believe it is. With the picture behind them, a ground
/// point sitting on a cat's back instead of its feet is obvious at a glance, and that is
/// the difference between a calibration that works and one that aims metres wide.
///
/// The layer shows the buffer in its native orientation and is then turned by the same
/// quarter turns `FrameGeometry` applies, so the picture and the overlay agree by
/// construction rather than by coincidence.
struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.backgroundColor = .black
        // Never stretch. `.resize` fills the layer regardless of the video's own shape, so
        // any error in the box it is given comes out as a distorted picture -- which is
        // worse than useless here, because a stretched frame moves every overlay box and
        // ground point away from the thing it is meant to sit on, and this view exists to
        // make exactly that kind of mistake visible. `.resizeAspect` keeps the picture
        // honest: when the box is right it fills it exactly and nothing is letterboxed, and
        // when it is wrong the bars say so instead of the animal changing shape.
        view.layer.videoGravity = .resizeAspect
        view.layer.session = session
        return view
    }

    func updateUIView(_ view: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        // swiftlint:disable:next force_cast
        override var layer: AVCaptureVideoPreviewLayer { super.layer as! AVCaptureVideoPreviewLayer }

        /// Forced here rather than once at construction, because at construction the layer
        /// has no connection yet — the session has only just been handed over — so setting
        /// it there silently did nothing and the layer kept its portrait default. The data
        /// output delivers the sensor's native 1920x1080, so the preview has to be told to
        /// present the same way or the picture is turned a quarter relative to every box
        /// drawn over it: the video ends up pillarboxed in a narrow strip while the overlay
        /// spans the full width, and a track lands nowhere near the animal.
        override func layoutSubviews() {
            super.layoutSubviews()
            guard let connection = layer.connection,
                  connection.isVideoOrientationSupported,
                  connection.videoOrientation != .landscapeRight else { return }
            connection.videoOrientation = .landscapeRight
        }
    }
}
