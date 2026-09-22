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

    private func makeLink() -> (ActuatorLink, FakeTransport, TestClock) {
        let transport = FakeTransport()
        let clock = TestClock()
        return (ActuatorLink(transport: transport, clock: clock), transport, clock)
    }

    func testTheHeartbeatGoesOutOnSchedule() {
        let (link, transport, _) = makeLink()
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
        let (link, transport, _) = makeLink()
        transport.isConnected = false
        link.tick(uptime: 0)
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testAStatusIsDecodedAndOffered() throws {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 10
        transport.deliver(healthyStatus() + Data("\n".utf8))

        let status = try XCTUnwrap(link.status(asOf: 10.5))
        XCTAssertTrue(status.armed)
        XCTAssertEqual(status.shots, 3)
        XCTAssertTrue(status.canFire)
    }

    func testAStaleStatusIsWithheld() {
        // The whole point of this class.
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 10
        transport.deliver(healthyStatus() + Data("\n".utf8))

        XCTAssertNotNil(link.status(asOf: 12.0))
        XCTAssertNil(link.status(asOf: 13.0), "a status older than maxStatusAge must not be offered")
    }

    func testDisconnectingDropsTheStatusImmediately() {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 10
        transport.deliver(healthyStatus() + Data("\n".utf8))
        XCTAssertNotNil(link.status(asOf: 10.1))

        transport.setConnected(false)
        XCTAssertNil(link.status(asOf: 10.2), "a dropped link cannot vouch for anything")
    }

    func testAMessageSplitAcrossTwoDeliveriesIsReassembled() throws {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        let whole = healthyStatus() + Data("\n".utf8)
        clock.uptime = 5
        transport.deliver(whole.prefix(20))
        XCTAssertNil(link.status(asOf: 5.1))
        clock.uptime = 5.2
        transport.deliver(whole.dropFirst(20))

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
    }

    func testTwoMessagesInOneDeliveryBothArrive() throws {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        let ack = Data("{\"ack\":\"park\",\"ok\":true}\n".utf8)
        clock.uptime = 5
        transport.deliver(ack + healthyStatus() + Data("\n".utf8))

        XCTAssertEqual(link.lastAck?.command, "park")
        XCTAssertNotNil(link.status(asOf: 5.1))
    }

    func testGarbageDoesNotDisturbTheLink() throws {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 5
        transport.deliver(Data("not json at all\n".utf8))
        clock.uptime = 5.1
        transport.deliver(Data("{\"unknown\":1}\n".utf8))
        clock.uptime = 5.2
        transport.deliver(healthyStatus() + Data("\n".utf8))

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
        XCTAssertEqual(link.malformedMessages, 2)
    }

    func testAnOverlongLineIsDiscardedRatherThanBuffered() {
        // A transport that never delivers a newline must not grow the buffer without bound.
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 5
        transport.deliver(Data(repeating: 0x41, count: 8192))

        XCTAssertLessThanOrEqual(link.bufferedBytes, ActuatorLink.maxMessageBytes)
    }

    func testRefusalsAreCounted() {
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 5
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8))
        clock.uptime = 6
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8))
        clock.uptime = 7
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"tank\"}\n".utf8))

        XCTAssertEqual(link.refusals["cooldown"], 2)
        XCTAssertEqual(link.refusals["tank"], 1)
    }

    func testACommandThatCannotBeEncodedIsReportedNotSent() {
        let (link, transport, _) = makeLink()
        transport.isConnected = true
        XCTAssertThrowsError(try link.send(.aim(pan: .nan, tilt: 0)))
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testFramingIsTheTransportsBusiness() throws {
        // The serial console reads one JSON object per line; BLE carries one object per
        // write and needs no terminator at all, with 180 bytes to spend. The link must not
        // decide this for both of them.
        let (link, transport, _) = makeLink()
        transport.isConnected = true
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[0], "{\"c\":\"park\"}")

        transport.framing = .newlineTerminated
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[1], "{\"c\":\"park\"}\n")
    }

    func testAClockRewindDoesNotPermanentlyWithholdEveryStatus() throws {
        // The link used to stamp an arriving status from ProcessInfo.systemUptime while
        // status(asOf:) was asked about an uptime from SteadyClock. The two agree until
        // SteadyClock compensates for a rewind, and then never again: every status reads
        // as far older than maxStatusAge and is withheld for the rest of the process's
        // life, silently, with nothing logged. Sharing one clock is what makes this pass.
        let raw = TestClock()
        let steady = SteadyClock(wrapping: raw)
        let transport = FakeTransport()
        transport.isConnected = true
        let link = ActuatorLink(transport: transport, clock: steady)

        raw.uptime = 100
        _ = steady.uptime
        raw.uptime = 40            // the glitch SteadyClock exists to absorb
        let afterGlitch = steady.uptime
        XCTAssertEqual(steady.anomalies, 1)

        transport.deliver(healthyStatus() + Data("\n".utf8))
        XCTAssertNotNil(link.status(asOf: afterGlitch), "a status that just arrived must not read as stale")
    }

    func testAMessageAfterAnOverlongRunIsStillRead() throws {
        // The buffer used to keep the tail of an over-long message, on the theory that it
        // gave the next real message a clean start. Measured, it did the opposite: the
        // tail merged with the next message and swallowed it too, so one overrun cost two
        // messages. Only the second message after the overrun survived.
        let (link, transport, clock) = makeLink()
        transport.isConnected = true
        clock.uptime = 5

        transport.deliver(Data(repeating: 0x41, count: 8192))
        transport.deliver(Data("\n".utf8))                       // ends the over-long run
        transport.deliver(healthyStatus() + Data("\n".utf8))     // the very next message

        XCTAssertNotNil(link.status(asOf: 5.1), "the first message after an overrun was lost")
        XCTAssertEqual(link.malformedMessages, 1, "only the over-long message should count")
    }

    func testBytesArrivingWhileDownAreNotBelieved() throws {
        // status(asOf:) re-checks the connection flag, but only the current one. A
        // transport that reconnected without announcing it could otherwise present a
        // status from a session that has already ended as though it were live.
        let (link, transport, clock) = makeLink()
        transport.isConnected = false
        clock.uptime = 5
        transport.deliver(healthyStatus() + Data("\n".utf8))

        transport.isConnected = true
        XCTAssertNil(link.status(asOf: 5.1), "a status from a dead session must not survive a silent reconnect")
    }
}

