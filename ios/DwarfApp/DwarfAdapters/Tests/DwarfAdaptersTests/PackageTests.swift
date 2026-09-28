import XCTest
import DwarfCore
@testable import DwarfAdapters

final class PackageTests: XCTestCase {
    func testDwarfCoreIsLinkedAndUsable() {
        // The whole point of this package is to feed DwarfCore. If the relative path in
        // Package.swift is wrong, this is where it is discovered, rather than three tasks
        // later inside a CoreML wrapper.
        let cycle = Cycle(calibration: .empty)
        let frame = GrayFrame(width: 4, height: 4, pixels: [UInt8](repeating: 10, count: 16))
        let output = cycle.process(frame: frame, detector: .pending, status: nil,
                                   now: Date(), uptime: 0)

        // Dark frame, no calibration, no detections: nothing to do, and nothing to park
        // from either, since the head has never moved.
        XCTAssertEqual(output.decision, .none)
        XCTAssertTrue(output.tracks.isEmpty)
    }
}
