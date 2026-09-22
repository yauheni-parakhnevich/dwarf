import XCTest
import DwarfCore
@testable import DwarfAdapters

final class ActuatorLinkTests: XCTestCase {
    private func healthyStatus() -> Data {
        Data("""
        {"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":true,"charge":false,\
        "fan":false,"temp":22,"fault":null,"shots":3}
        """.utf8)
    }

    private func makeLink() -> (ActuatorLink, FakeTransport) {
        let transport = FakeTransport()
        return (ActuatorLink(transport: transport), transport)
    }

    func testTheHeartbeatGoesOutOnSchedule() {
        let (link, transport) = makeLink()
        transport.isConnected = true

        link.tick(uptime: 0)
        link.tick(uptime: 0.5)
        link.tick(uptime: 1.1)

        let beats = transport.sentStrings.filter { $0.contains("\"hb\"") }
        XCTAssertEqual(beats.count, 2, "one at zero, one past the interval: \(transport.sentStrings)")
    }

    func testNoHeartbeatGoesOutWhileDisconnected() {
        // Writing into a dead transport is how a queue backs up and then floods the moment
        // the link returns.
        let (link, transport) = makeLink()
        transport.isConnected = false
        link.tick(uptime: 0)
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testAStatusIsDecodedAndOffered() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)

        let status = try XCTUnwrap(link.status(asOf: 10.5))
        XCTAssertTrue(status.armed)
        XCTAssertEqual(status.shots, 3)
        XCTAssertTrue(status.canFire)
    }

    func testAStaleStatusIsWithheld() {
        // The whole point of this class.
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)

        XCTAssertNotNil(link.status(asOf: 12.0))
        XCTAssertNil(link.status(asOf: 13.0), "a status older than maxStatusAge must not be offered")
    }

    func testDisconnectingDropsTheStatusImmediately() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)
        XCTAssertNotNil(link.status(asOf: 10.1))

        transport.setConnected(false)
        XCTAssertNil(link.status(asOf: 10.2), "a dropped link cannot vouch for anything")
    }

    func testAMessageSplitAcrossTwoDeliveriesIsReassembled() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        let whole = healthyStatus() + Data("\n".utf8)
        transport.deliver(whole.prefix(20), at: 5)
        XCTAssertNil(link.status(asOf: 5.1))
        transport.deliver(whole.dropFirst(20), at: 5.2)

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
    }

    func testTwoMessagesInOneDeliveryBothArrive() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        let ack = Data("{\"ack\":\"park\",\"ok\":true}\n".utf8)
        transport.deliver(ack + healthyStatus() + Data("\n".utf8), at: 5)

        XCTAssertEqual(link.lastAck?.command, "park")
        XCTAssertNotNil(link.status(asOf: 5.1))
    }

    func testGarbageDoesNotDisturbTheLink() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data("not json at all\n".utf8), at: 5)
        transport.deliver(Data("{\"unknown\":1}\n".utf8), at: 5.1)
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 5.2)

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
        XCTAssertEqual(link.malformedMessages, 2)
    }

    func testAnOverlongLineIsDiscardedRatherThanBuffered() {
        // A transport that never delivers a newline must not grow the buffer without bound.
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data(repeating: 0x41, count: 8192), at: 5)

        XCTAssertLessThanOrEqual(link.bufferedBytes, ActuatorLink.maxMessageBytes)
    }

    func testRefusalsAreCounted() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8), at: 5)
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8), at: 6)
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"tank\"}\n".utf8), at: 7)

        XCTAssertEqual(link.refusals["cooldown"], 2)
        XCTAssertEqual(link.refusals["tank"], 1)
    }

    func testACommandThatCannotBeEncodedIsReportedNotSent() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        XCTAssertThrowsError(try link.send(.aim(pan: .nan, tilt: 0)))
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testFramingIsTheTransportsBusiness() throws {
        // The serial console reads one JSON object per line; BLE carries one object per
        // write and needs no terminator at all, with 180 bytes to spend. The link must not
        // decide this for both of them.
        let (link, transport) = makeLink()
        transport.isConnected = true
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[0], "{\"c\":\"park\"}")

        transport.framing = .newlineTerminated
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[1], "{\"c\":\"park\"}\n")
    }
}
