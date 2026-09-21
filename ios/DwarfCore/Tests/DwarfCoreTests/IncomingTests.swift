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
}
