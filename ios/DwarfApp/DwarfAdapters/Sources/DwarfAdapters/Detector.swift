import Foundation
import CoreML
import CoreVideo
import DwarfCore

/// One box as the model gave it, normalised to the model's square input. Turning this into
/// frame coordinates is `Letterbox`'s job, and it needs to know which crop it came from.
public struct RawBox: Equatable, Sendable {
    public let box: Rect
    public let confidence: Double

    public init(box: Rect, confidence: Double) {
        self.box = box
        self.confidence = confidence
    }
}

public enum DetectorError: Error, Equatable {
    case modelMissing(name: String)
    case unexpectedOutputs
}

/// Anything that can look at a square image and say where the cats are.
public protocol Detector: AnyObject {
    /// Blocking. Callers run this off the capture queue.
    func detect(input: CVPixelBuffer) throws -> [RawBox]
}

/// Reads Ultralytics' CoreML export.
///
/// The export with `nms=True` produces two tensors: `confidence`, shaped rows × 80, one
/// column per COCO class, and `coordinates`, shaped rows × 4, each row being centre x,
/// centre y, width and height normalised to the model's square input. Non-maximum
/// suppression has already happened inside the model, so every row is a distinct object.
public enum BoxDecoder {
    /// COCO's class order: person 0, …, bird 14, cat 15, dog 16.
    public static let catClassIndex = 15

    public static func decode(confidence: MLMultiArray, coordinates: MLMultiArray,
                              minConfidence: Double) -> [RawBox] {
        guard confidence.shape.count == 2, coordinates.shape.count == 2 else { return [] }
        let rows = confidence.shape[0].intValue
        let classes = confidence.shape[1].intValue
        guard coordinates.shape[0].intValue == rows,
              coordinates.shape[1].intValue == 4,
              classes > catClassIndex else { return [] }

        var boxes: [RawBox] = []
        boxes.reserveCapacity(rows)
        for row in 0..<rows {
            let score = confidence[row * classes + catClassIndex].doubleValue
            guard score >= minConfidence else { continue }

            let centreX = coordinates[row * 4 + 0].doubleValue
            let centreY = coordinates[row * 4 + 1].doubleValue
            let width = coordinates[row * 4 + 2].doubleValue
            let height = coordinates[row * 4 + 3].doubleValue

            // A non-finite box poisons every distance the tracker computes, and comparisons
            // against NaN are false in a way that reads as "not too close". Dropping the
            // row costs one look; letting it through costs the guarantee.
            guard centreX.isFinite, centreY.isFinite, width.isFinite, height.isFinite,
                  width > 0, height > 0, score.isFinite else { continue }

            boxes.append(RawBox(box: Rect(x: centreX - width / 2, y: centreY - height / 2,
                                          width: width, height: height),
                                confidence: score))
        }
        return boxes
    }
}

/// A detector that answers with whatever it was told to, so a runtime can be driven end to
/// end on a Mac.
public final class FakeDetector: Detector {
    public var next: [RawBox] = []
    public private(set) var calls = 0
    /// Set to have `detect` throw, for testing what a failed inference does to the loop.
    public var error: Error?

    public init() {}

    public func detect(input: CVPixelBuffer) throws -> [RawBox] {
        calls += 1
        if let error { throw error }
        return next
    }

    /// A blank square, for tests that need an input to hand over.
    public static func blankInput(side: Int) -> CVPixelBuffer? {
        var buffer: CVPixelBuffer?
        guard CVPixelBufferCreate(kCFAllocatorDefault, side, side, kCVPixelFormatType_32BGRA,
                                  nil, &buffer) == kCVReturnSuccess else { return nil }
        return buffer
    }
}
