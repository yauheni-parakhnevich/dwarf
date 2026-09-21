import XCTest
@testable import DwarfCore

/// Cross-checks this package against the same fixture files the ESP32 firmware's tests use.
/// If these fail, the two halves of the project have drifted apart.
final class FixtureTests: XCTestCase {
    /// Walk up from this source file to the repository root. Using #filePath rather than
    /// bundled resources keeps one copy of the fixtures, shared with the firmware.
    private func fixture(_ name: String) throws -> [String: String] {
        let here = URL(fileURLWithPath: #filePath)
        let root = here
            .deletingLastPathComponent()   // DwarfCoreTests
            .deletingLastPathComponent()   // Tests
            .deletingLastPathComponent()   // DwarfCore
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
        let url = root.appendingPathComponent("protocol/fixtures/\(name).json")
        let data = try Data(contentsOf: url)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
    }

    func testEveryStatusFixtureDecodes() throws {
        for (name, text) in try fixture("status") {
            let message = try IncomingMessage.decode(Data(text.utf8))
            switch (name, message) {
            case ("ack_reject", .ack(let ack)):
                XCTAssertFalse(ack.ok)
                XCTAssertEqual(ack.why, "cooldown")
            case ("ack_ok", .ack(let ack)):
                XCTAssertTrue(ack.ok)
                XCTAssertNil(ack.why)
            case ("idle", .status(let status)):
                XCTAssertFalse(status.armed)
                XCTAssertNil(status.fault)
            case ("tank_empty", .status(let status)):
                XCTAssertEqual(status.fault, .tankEmpty)
                XCTAssertFalse(status.tankOk)
            case ("overtemp", .status(let status)):
                XCTAssertEqual(status.fault, .overtemp)
            case ("valve_timeout", .status(let status)):
                XCTAssertEqual(status.fault, .valveTimeout)
                XCTAssertTrue(status.tankOk)
            case ("temp_sensor", .status(let status)):
                // The dead/disconnected probe case: the firmware serialises a non-finite
                // temperature as JSON null (see protocol.cpp's round1/writeJson path and
                // test_format_status_nonfinite_and_sentinel_temp), which this decoder
                // reads back as NaN rather than treating the field as missing.
                XCTAssertEqual(status.fault, .tempSensor)
                XCTAssertTrue(status.temp.isNaN)
            case ("armed_shooting", .status(let status)):
                XCTAssertTrue(status.armed)
                XCTAssertTrue(status.pump)
                XCTAssertEqual(status.shots, 12)
            default:
                XCTFail("unhandled fixture \(name): add a case so new fixtures cannot slip in unchecked")
            }
        }
    }

    func testOurCommandsMatchTheCommandFixtures() throws {
        let fixtures = try fixture("commands")

        func assertMatches(_ command: Command, _ name: String,
                           file: StaticString = #filePath, line: UInt = #line) throws {
            let expectedText = try XCTUnwrap(fixtures[name], "missing fixture \(name)", file: file, line: line)
            let expected = try XCTUnwrap(
                JSONSerialization.jsonObject(with: Data(expectedText.utf8)) as? [String: Any],
                file: file, line: line)
            let actual = try XCTUnwrap(
                JSONSerialization.jsonObject(with: command.encoded()) as? [String: Any],
                file: file, line: line)

            XCTAssertEqual(Set(expected.keys), Set(actual.keys), "keys differ for \(name)",
                           file: file, line: line)
            for key in expected.keys {
                let lhs = expected[key], rhs = actual[key]
                if let l = lhs as? String, let r = rhs as? String {
                    XCTAssertEqual(l, r, "\(name).\(key)", file: file, line: line)
                } else if let l = lhs as? Bool, let r = rhs as? Bool {
                    XCTAssertEqual(l, r, "\(name).\(key)", file: file, line: line)
                } else if let l = lhs as? NSNumber, let r = rhs as? NSNumber {
                    XCTAssertEqual(l.doubleValue, r.doubleValue, accuracy: 1e-9,
                                   "\(name).\(key)", file: file, line: line)
                } else {
                    XCTFail("type mismatch for \(name).\(key)", file: file, line: line)
                }
            }
        }

        try assertMatches(.heartbeat, "hb")
        try assertMatches(.arm(true), "arm_on")
        try assertMatches(.arm(false), "arm_off")
        try assertMatches(.aim(pan: 12.5, tilt: -3.0), "aim")
        try assertMatches(.park, "park")
        try assertMatches(.shoot(pan: 14.0, tilt: -2.5, ms: 300), "shoot")
        try assertMatches(.charge(false), "charge_off")
        try assertMatches(.fan(true), "fan_on")
        // Built from AimLimits' own defaults rather than from literals typed in here, so
        // that the shared fixture is pinned to the travel limits this package actually
        // operates with. The firmware's test does the same against its `Limits` defaults,
        // which is what makes the fixture a real cross-check of the numbers and not only
        // of the message shape: if either side's limits drift, that side's test fails.
        let limits = AimLimits()
        try assertMatches(.config(panMin: limits.panMin, panMax: limits.panMax,
                                  tiltMin: limits.tiltMin, tiltMax: limits.tiltMax), "cfg")
    }
}
