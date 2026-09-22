import Foundation
import CoreML
import CoreVideo

/// The exported YOLO11n, loaded from the app bundle.
///
/// Deliberately thin: it feeds a pixel buffer in and hands the two output tensors to
/// `BoxDecoder`. Everything worth arguing about is in the decoder, which is tested on a
/// Mac; what is left here can only be exercised on the phone, and Task 6 does that.
public final class CoreMLDetector: Detector {
    private let model: MLModel
    private let imageInputName: String
    private let minConfidence: Double
    private let iouThreshold: Double

    /// - Parameter computeUnits: the A9 has no Neural Engine, so `.all` means GPU with a
    ///   CPU fallback. Left configurable because M0 may find the CPU steadier under
    ///   thermal pressure than a GPU competing with the camera.
    public init(modelName: String = "yolo11n", bundle: Bundle = .main,
                minConfidence: Double = 0.25, iouThreshold: Double = 0.45,
                computeUnits: MLComputeUnits = .all) throws {
        guard let url = bundle.url(forResource: modelName, withExtension: "mlmodelc") else {
            throw DetectorError.modelMissing(name: modelName)
        }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = computeUnits
        self.model = try MLModel(contentsOf: url, configuration: configuration)
        self.minConfidence = minConfidence
        self.iouThreshold = iouThreshold

        // The export has three inputs, not one: `image`, `iouThreshold` and
        // `confidenceThreshold`. Picking `keys.first` would hand a pixel buffer to
        // whichever of them a Dictionary happened to enumerate first — a bug that works
        // on the bench and fails in the garden, or the other way round. Select by type.
        let inputs = model.modelDescription.inputDescriptionsByName
        guard let image = inputs.first(where: { $0.value.type == .image })?.key else {
            throw DetectorError.unexpectedOutputs
        }
        self.imageInputName = image
    }

    public func detect(input: CVPixelBuffer) throws -> [RawBox] {
        // None of the three inputs is optional in the spec, so all three are supplied.
        // Thresholding inside the model is also cheaper: suppressed boxes never become
        // rows for BoxDecoder to walk. It still checks the confidence itself, because a
        // re-export with different defaults should not quietly widen what gets fired at.
        let features = try MLDictionaryFeatureProvider(dictionary: [
            imageInputName: MLFeatureValue(pixelBuffer: input),
            "iouThreshold": MLFeatureValue(double: iouThreshold),
            "confidenceThreshold": MLFeatureValue(double: minConfidence)
        ])
        let output = try model.prediction(from: features)

        guard let confidence = output.featureValue(for: "confidence")?.multiArrayValue,
              let coordinates = output.featureValue(for: "coordinates")?.multiArrayValue else {
            throw DetectorError.unexpectedOutputs
        }
        return try BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                     minConfidence: minConfidence)
    }
}
