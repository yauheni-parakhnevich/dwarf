import XCTest
@testable import DwarfCore

final class IncomingTests: XCTestCase {
    private func decode(_ text: String) throws -> IncomingMessage {
        try IncomingMessage.decode(Data(text.utf8))
    }

    func testDecodesStatus() throws {
        let message = try decode(#"{"armed":true,"pan":12.5,"tilt":-3,"tank":"ok","pump":true,"charge":false,"fan":false,"temp":31.3,"fault":null,"shots":12}"#)
        guard case .status(let status) = message else { return XCTFail("expected status") }

        XCTAssertTrue(status.armed)
        XCTAssertEqual(status.pan, 12.5, accuracy: 1e-9)
        XCTAssertEqual(status.tilt, -3, accuracy: 1e-9)
        XCTAssertTrue(status.tankOk)
        XCTAssertTrue(status.pump)
        XCTAssertFalse(status.charge)
        XCTAssertEqual(status.temp, 31.3, accuracy: 1e-9)
        XCTAssertNil(status.fault)
        XCTAssertEqual(status.shots, 12)
    }

    func testDecodesEveryFaultCode() throws {
        let codes: [(String, DeviceFault)] = [
            ("TANK_EMPTY", .tankEmpty), ("OVERTEMP", .overtemp),
            ("TEMP_SENSOR", .tempSensor), ("VALVE_TIMEOUT", .valveTimeout)
        ]
        for (text, expected) in codes {
            let message = try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"low","pump":false,"charge":true,"fan":false,"temp":24,"fault":"\#(text)","shots":3}"#)
            guard case .status(let status) = message else { return XCTFail("expected status") }
            XCTAssertEqual(status.fault, expected)
            XCTAssertFalse(status.tankOk)
        }
    }

    func testAnUnknownFaultCodeDecodesAsUnknownRatherThanFailing() throws {
        // A newer firmware must not make the app blind to the rest of the status.
        let message = try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":"FUTURE_FAULT","shots":0}"#)
        guard case .status(let status) = message else { return XCTFail("expected status") }
        XCTAssertEqual(status.fault, .unknown("FUTURE_FAULT"))
    }

    func testDecodesRejectAck() throws {
        let message = try decode(#"{"ack":"shoot","ok":false,"why":"cooldown"}"#)
        guard case .ack(let ack) = message else { return XCTFail("expected ack") }

        XCTAssertEqual(ack.command, "shoot")
        XCTAssertFalse(ack.ok)
        XCTAssertEqual(ack.why, "cooldown")
    }

    func testDecodesSuccessAckWithoutWhy() throws {
        let message = try decode(#"{"ack":"arm","ok":true}"#)
        guard case .ack(let ack) = message else { return XCTFail("expected ack") }
        XCTAssertTrue(ack.ok)
        XCTAssertNil(ack.why)
    }

    func testRejectsGarbage() {
        XCTAssertThrowsError(try decode("not json"))
        XCTAssertThrowsError(try decode("{}"))
        XCTAssertThrowsError(try decode(#"{"hello":"world"}"#))
    }

    func testRejectsAStatusMissingAField() {
        XCTAssertThrowsError(try decode(#"{"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":20,"fault":null}"#),
                             "shots is missing")
    }

    // MARK: - "shots" narrowing must never trap the process.
    //
    // `UInt32(_:)` does not throw on a value it cannot represent -- it hits a fatal-error
    // trap and takes the whole process down with it. A single corrupted BLE notification
    // that still parses as valid JSON must not be able to kill the app that way, so these
    // values must come back as a catchable `DecodingError`, never a crash.

    func testNegativeShotsIsRejectedRatherThanTrappingTheProcess() {
        XCTAssertThrowsError(try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":null,"shots":-1}"#)) { error in
            guard case IncomingMessage.DecodingError.outOfRange(let field, _) = error else {
                return XCTFail("expected outOfRange, got \(error)")
            }
            XCTAssertEqual(field, "shots")
        }
    }

    func testShotsAboveUInt32MaxIsRejectedRatherThanTrappingTheProcess() {
        let tooLarge = Double(UInt32.max) + 1
        XCTAssertThrowsError(try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":null,"shots":\#(tooLarge)}"#)) { error in
            guard case IncomingMessage.DecodingError.outOfRange(let field, _) = error else {
                return XCTFail("expected outOfRange, got \(error)")
            }
            XCTAssertEqual(field, "shots")
        }
    }

    func testNonFiniteShotsIsRejectedRatherThanTrappingTheProcess() {
        // The firmware never actually sends a null "shots" -- it is serialised straight
        // from a uint32_t, never through the round1() helper that turns pan/tilt/temp
        // into null when non-finite -- but a corrupted packet is a corrupted packet
        // regardless of what the firmware would ever intentionally emit.
        XCTAssertThrowsError(try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":null,"shots":null}"#)) { error in
            guard case IncomingMessage.DecodingError.outOfRange(let field, let value) = error else {
                return XCTFail("expected outOfRange, got \(error)")
            }
            XCTAssertEqual(field, "shots")
            XCTAssertTrue(value.isNaN)
        }
    }

    func testFractionalShotsTruncatesDeliberately() throws {
        // An in-range fractional count truncates toward zero -- the same truncation
        // UInt32(_:) itself would perform -- rather than being rejected outright.
        let message = try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":null,"shots":3.7}"#)
        guard case .status(let status) = message else { return XCTFail("expected status") }
        XCTAssertEqual(status.shots, 3)
    }
}
