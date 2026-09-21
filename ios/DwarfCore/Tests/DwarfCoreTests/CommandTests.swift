import XCTest
@testable import DwarfCore

final class CommandTests: XCTestCase {
    private func json(_ command: Command) throws -> [String: Any] {
        let data = try command.encoded()
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testHeartbeat() throws {
        XCTAssertEqual(try json(.heartbeat)["c"] as? String, "hb")
        XCTAssertEqual(try json(.heartbeat).count, 1)
    }

    func testArm() throws {
        let object = try json(.arm(true))
        XCTAssertEqual(object["c"] as? String, "arm")
        XCTAssertEqual(object["v"] as? Bool, true)
    }

    func testAim() throws {
        let object = try json(.aim(pan: 12.5, tilt: -3))
        XCTAssertEqual(object["c"] as? String, "aim")
        XCTAssertEqual(object["pan"] as? Double, 12.5)
        XCTAssertEqual(object["tilt"] as? Double, -3)
    }

    func testShootEncodesMsAsAnInteger() throws {
        let data = try Command.shoot(pan: 14, tilt: -2.5, ms: 300).encoded()
        let text = try XCTUnwrap(String(data: data, encoding: .utf8))

        // The firmware rejects "ms":300.0 outright, so this is not cosmetic.
        XCTAssertTrue(text.contains("\"ms\":300"), text)
        XCTAssertFalse(text.contains("300.0"), text)
    }

    func testPark() throws {
        XCTAssertEqual(try json(.park)["c"] as? String, "park")
    }

    func testChargeAndFan() throws {
        XCTAssertEqual(try json(.charge(false))["v"] as? Bool, false)
        XCTAssertEqual(try json(.fan(true))["c"] as? String, "fan")
    }

    func testConfig() throws {
        let object = try json(.config(panMin: -60, panMax: 60, tiltMin: -30, tiltMax: 40))
        XCTAssertEqual(object["c"] as? String, "cfg")
        XCTAssertEqual(object["panMin"] as? Double, -60)
        XCTAssertEqual(object["tiltMax"] as? Double, 40)
    }

    func testNonFiniteAnglesAreRefused() {
        XCTAssertThrowsError(try Command.aim(pan: .nan, tilt: 0).encoded())
        XCTAssertThrowsError(try Command.aim(pan: .infinity, tilt: 0).encoded())
        XCTAssertThrowsError(try Command.shoot(pan: 0, tilt: -.infinity, ms: 300).encoded())
        XCTAssertThrowsError(try Command.config(panMin: -60, panMax: .nan, tiltMin: -30, tiltMax: 40).encoded())
    }

    func testZeroLengthBurstIsRefused() {
        // The firmware rejects it too, but there is no reason to spend a BLE round trip
        // discovering that.
        XCTAssertThrowsError(try Command.shoot(pan: 0, tilt: 0, ms: 0).encoded())
    }

    func testEveryMessageFitsOneBLEWrite() throws {
        let commands: [Command] = [
            .heartbeat, .arm(true), .aim(pan: -59.9, tilt: -29.9), .park,
            .shoot(pan: -59.9, tilt: 39.9, ms: 500), .charge(false), .fan(true),
            .config(panMin: -60, panMax: 60, tiltMin: -30, tiltMax: 40)
        ]
        for command in commands {
            XCTAssertLessThanOrEqual(try command.encoded().count, 180, "\(command)")
        }
    }
}
