import Foundation

/// Where a link stands with respect to the gnome's BLE bonding requirement.
///
/// Pulled out of `BluetoothTransport` deliberately. `BluetoothTransport` lives in the app
/// target and can only ever be exercised against a real radio, but the *rules* for telling
/// "no gnome found" apart from "the gnome is there and refusing us for want of a bond" do
/// not need one — they only need a stream of events a radio happens to be one source of.
/// That makes them exactly the kind of thing worth getting right under a fake before ever
/// touching hardware, which is what `PairingTrackerTests` does.
///
/// The firmware requires bonding with LE Secure Connections and a passkey for both
/// characteristics (see the BLE access-control comment block in `firmware/src/main.cpp`),
/// and disconnects any central that has not authenticated within ten seconds
/// (`dropUnauthenticated`), to stop strangers squatting on its connection slots. That second
/// fact matters here as much as the first: without it, a connection that keeps dropping
/// about ten seconds after it forms would look exactly like a flaky link, when it actually
/// means pairing is not completing.
public final class PairingTracker {
    /// True while the gnome is reachable but has refused every write or subscription this
    /// connection has attempted, for want of a bond. A different instruction to the owner
    /// than "not connected": pair with it, using the passkey printed on the gnome's serial
    /// console on every boot.
    public private(set) var needsPairing = false

    /// The firmware's own `kAuthGraceMs`, plus a margin for BLE's connection-setup time and
    /// callback jitter, so a pairing that completes just inside the firmware's window is
    /// never misread as a fast bounce.
    ///
    /// That grace period was ten seconds until the first attempt to pair a real phone, which
    /// this guard evicted twice mid-dialog: ten seconds is ample for two machines and
    /// hopeless for a person reading a six-digit number and typing it. It is a minute now,
    /// and this constant follows it — a disconnect the firmware caused for want of
    /// authentication is exactly what tells the app to say "pair with me" rather than
    /// "no gnome here", and it can only say that if it recognises the bounce.
    public static let quickDisconnectThreshold: TimeInterval = 65

    private var connectedAtUptime: TimeInterval?
    /// Reset on every fresh connection, not held forever once true. A bond that was good
    /// five minutes ago says nothing about a central connecting right now: the firmware's
    /// serial `erase-bonds` escape hatch (see `firmware/src/main.cpp`) can make a phone that
    /// authenticated earlier in this same process need to pair again.
    private var authenticatedThisConnection = false

    public init() {}

    /// A radio-level link just formed. Nothing is known yet about whether it will be let
    /// through — that is what the rest of this connection's events are for.
    public func connected(atUptime uptime: TimeInterval) {
        connectedAtUptime = uptime
        authenticatedThisConnection = false
    }

    /// A radio-level link just ended, for whatever reason: the phone went out of range, the
    /// gnome lost power, or — the case this exists to catch — the firmware's ten-second
    /// authentication grace period expired and it showed the door to a central that never
    /// proved itself.
    ///
    /// `needsPairing` is left exactly as it was unless *this* disconnect itself looks like a
    /// pairing failure. That matters as much as detecting the failure in the first place: an
    /// owner watching a gnome that connects, sits for a few seconds, and drops, over and
    /// over, needs to see one steady "needs pairing" through that whole cycle. Clearing the
    /// flag between attempts would show "no link" for the gap between each retry, which
    /// reads as a flaky connection — precisely the diagnosis this type exists to rule out.
    public func disconnected(atUptime uptime: TimeInterval) {
        if let connectedAt = connectedAtUptime,
           !authenticatedThisConnection,
           uptime - connectedAt < Self.quickDisconnectThreshold {
            needsPairing = true
        }
        connectedAtUptime = nil
        authenticatedThisConnection = false
    }

    /// A write or subscription came back `CBATTError.insufficientAuthentication` or
    /// `.insufficientEncryption`. Unambiguous — no need to wait for the firmware to give up
    /// and disconnect before saying so.
    public func authenticationFailed() {
        needsPairing = true
    }

    /// A write succeeded, or a notification arrived. Either one is only possible over a link
    /// the gnome has encrypted and authenticated — `status` is `READ_ENC | READ_AUTHEN` and
    /// NimBLE's `notify()` silently skips any subscriber whose link is not encrypted, and
    /// `cmd`'s `WRITE_ENC | WRITE_AUTHEN` means an unauthenticated write never even reaches
    /// the firmware's callback — so either is proof the gnome now trusts this phone.
    public func authenticationSucceeded() {
        needsPairing = false
        authenticatedThisConnection = true
    }
}
