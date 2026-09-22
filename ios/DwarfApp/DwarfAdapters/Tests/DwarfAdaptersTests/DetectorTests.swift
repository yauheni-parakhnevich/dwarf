import XCTest
import CoreML
import DwarfCore
@testable import DwarfAdapters

final class DetectorTests: XCTestCase {
    /// The shape Ultralytics' CoreML export with embedded NMS produces: confidences per
    /// class, and boxes as centre/size normalised to the model's square input.
    private func outputs(_ rows: [(cls: Int, confidence: Double, box: [Double])])
        throws -> (MLMultiArray, MLMultiArray) {
        let confidence = try MLMultiArray(shape: [NSNumber(value: rows.count), 80],
                                          dataType: .double)
        let coordinates = try MLMultiArray(shape: [NSNumber(value: rows.count), 4],
                                           dataType: .double)
        for i in 0..<(rows.count * 80) { confidence[i] = 0 }
        for (row, entry) in rows.enumerated() {
            confidence[row * 80 + entry.cls] = NSNumber(value: entry.confidence)
            for k in 0..<4 { coordinates[row * 4 + k] = NSNumber(value: entry.box[k]) }
        }
        return (confidence, coordinates)
    }

    func testACentreSizeBoxBecomesACornerBox() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.9, box: [0.5, 0.5, 0.2, 0.4])
        ])
        let boxes = BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                      minConfidence: 0.25)

        XCTAssertEqual(boxes.count, 1)
        XCTAssertEqual(boxes[0].box.x, 0.4, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.y, 0.3, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.width, 0.2, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.height, 0.4, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].confidence, 0.9, accuracy: 1e-9)
    }

    func testOnlyCatsSurvive() throws {
        // DwarfCore treats everything it is handed as a cat. A dog at 0.99 that reaches it
        // is a dog that gets sprayed.
        let (confidence, coordinates) = try outputs([
            (cls: 16, confidence: 0.99, box: [0.5, 0.5, 0.2, 0.2]),   // dog
            (cls: 0,  confidence: 0.95, box: [0.2, 0.2, 0.1, 0.1]),   // person
            (cls: BoxDecoder.catClassIndex, confidence: 0.6, box: [0.8, 0.8, 0.1, 0.1])
        ])
        let boxes = BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                      minConfidence: 0.25)

        XCTAssertEqual(boxes.count, 1)
        XCTAssertEqual(boxes[0].confidence, 0.6, accuracy: 1e-9)
    }

    func testLowConfidenceRowsAreDropped() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.1, box: [0.5, 0.5, 0.2, 0.2])
        ])
        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testMismatchedOrEmptyTensorsAreSurvivable() throws {
        // A model swapped for a different export should produce no detections, not a crash
        // in the middle of the garden.
        let confidence = try MLMultiArray(shape: [2, 80], dataType: .double)
        let coordinates = try MLMultiArray(shape: [1, 4], dataType: .double)
        for i in 0..<160 { confidence[i] = 0 }
        for i in 0..<4 { coordinates[i] = 0 }

        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testANonFiniteBoxIsDropped() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.9,
             box: [Double.nan, 0.5, 0.2, 0.2])
        ])
        // A NaN that reaches DwarfCore poisons the tracker's distances, and every
        // comparison against it is false in a way that reads as "in range".
        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testTheFakeDetectorReturnsWhatItWasGiven() throws {
        // The fake exists so later tasks can drive a whole runtime without a model.
        let fake = FakeDetector()
        fake.next = [RawBox(box: Rect(x: 0.1, y: 0.1, width: 0.2, height: 0.2), confidence: 0.8)]
        let buffer = try XCTUnwrap(FakeDetector.blankInput(side: 64))

        XCTAssertEqual(try fake.detect(input: buffer).count, 1)
        XCTAssertEqual(fake.calls, 1)
    }
}
