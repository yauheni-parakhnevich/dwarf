import XCTest
@testable import DwarfAdapters

/// `PairingTracker` is the one piece of the BLE story that does not need a radio to test:
/// it only ever sees a stream of events, and `BluetoothTransport` (untestable, in the app
/// target) is nothing more than a translator from CoreBluetooth's callbacks into these.
final class PairingTrackerTests: XCTestCase {
    func testStartsNotNeedingPairing() {
        XCTAssertFalse(PairingTracker().needsPairing)
    }

    func testAWriteFailingAuthenticationMeansPairingIsNeeded() {
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.authenticationFailed()
        XCTAssertTrue(tracker.needsPairing)
    }

    func testAWriteSucceedingClearsPairing() {
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.authenticationFailed()
        tracker.authenticationSucceeded()
        XCTAssertFalse(tracker.needsPairing)
    }

    func testADisconnectWellWithinTheFirmwaresTenSecondGraceMeansPairingIsNeeded() {
        // The firmware disconnects any central that has not authenticated within ten
        // seconds. A connection that dies at second 3 having never authenticated is that
        // happening, not a flaky link.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 100)
        tracker.disconnected(atUptime: 103)
        XCTAssertTrue(tracker.needsPairing)
    }

    func testADisconnectRightAtTheFirmwaresTenSecondMarkMeansPairingIsNeeded() {
        let tracker = PairingTracker()
        tracker.connected(atUptime: 100)
        tracker.disconnected(atUptime: 110)
        XCTAssertTrue(tracker.needsPairing, "ten seconds is exactly dropUnauthenticated's own grace period")
    }

    func testADisconnectAfterAuthenticatingIsNotMistakenForAPairingProblem() {
        // A link that authenticated and then dropped ten minutes later is an ordinary
        // disconnect — the phone walked away, or the gnome lost power — not a bond issue.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.authenticationSucceeded()
        tracker.disconnected(atUptime: 600)
        XCTAssertFalse(tracker.needsPairing)
    }

    func testAQuickDisconnectAfterAlreadyAuthenticatingThisConnectionIsNotMistakenForAPairingProblem() {
        // Authenticated fast, then dropped fast (e.g. the phone stepped out of range a
        // second after a bonded reconnect re-encrypted). The grace-period heuristic must not
        // fire just because the whole thing happened inside ten seconds.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.authenticationSucceeded()
        tracker.disconnected(atUptime: 2)
        XCTAssertFalse(tracker.needsPairing)
    }

    func testADisconnectPastTheGraceWindowWithNoAuthenticationIsNotMistakenForAPairingProblem() {
        // Outside the firmware's own window, a disconnect after never authenticating is not
        // the specific "pairing keeps not completing" pattern this heuristic looks for —
        // against the real firmware this should not happen at all (dropUnauthenticated would
        // already have closed it), so leaving needsPairing as it was is the honest answer.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.disconnected(atUptime: 30)
        XCTAssertFalse(tracker.needsPairing)
    }

    func testNeedsPairingPersistsThroughTheDisconnectSoTheOwnerSeesOneSteadyMessage() {
        // The whole point: an owner watching a gnome that connects, sits a few seconds and
        // drops, over and over, must see one steady "needs pairing", not a flicker back to
        // "no link" in the gap between each retry — that would read as a flaky connection.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.disconnected(atUptime: 5)
        XCTAssertTrue(tracker.needsPairing)

        tracker.connected(atUptime: 6)
        XCTAssertTrue(tracker.needsPairing, "reconnecting must not silently clear the flag before we know anything")
    }

    func testABondErasedMidSessionMakesTheNextConnectionNeedPairingAgainEvenThoughThisPhoneAuthenticatedBefore() {
        // firmware/src/main.cpp's serial "erase-bonds" escape hatch can make a previously
        // trusted phone need to pair again. Tracking authentication per connection, rather
        // than "ever", is what makes that show up correctly instead of being masked by a
        // stale "we've paired before" flag.
        let tracker = PairingTracker()
        tracker.connected(atUptime: 0)
        tracker.authenticationSucceeded()
        tracker.disconnected(atUptime: 500)
        XCTAssertFalse(tracker.needsPairing)

        // Bonds erased on the bench; the same phone reconnects and is refused all over again.
        tracker.connected(atUptime: 501)
        tracker.disconnected(atUptime: 505)
        XCTAssertTrue(tracker.needsPairing)
    }

    func testADisconnectWithNoPrecedingConnectDoesNothing() {
        // didFailToConnect can fire without a matching `connected` ever having been
        // reported. Nothing to compare against, so the quiet answer is the right one.
        let tracker = PairingTracker()
        tracker.disconnected(atUptime: 5)
        XCTAssertFalse(tracker.needsPairing)
    }
}
