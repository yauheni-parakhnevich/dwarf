import Foundation
import DwarfCore

public struct LinkConfig: Equatable, Sendable {
    /// The firmware disarms after 3 s of silence. One beat a second leaves room for two to
    /// be lost before that matters.
    public var heartbeatInterval: TimeInterval = 1.0
    /// How old a status may be and still be offered to `FirePolicy`. The gnome publishes on
    /// change and at least once a second, so 2.5 s is two missed publications.
    public var maxStatusAge: TimeInterval = 2.5

    public init() {}
}

/// Everything about talking to the gnome except the radio.
///
/// The one rule worth stating out loud: `status(asOf:)` returns nil rather than something
/// old. `FirePolicy` checks `status.canFire` and has no idea when that status was true, so
/// a cached "armed, tank fine, no fault" handed back after the link died would keep
/// authorising shots. The firmware's own watchdog means they would be refused rather than
/// fired, but each refusal still spends an animal's budget on water it never received.
public final class ActuatorLink {
    /// Longest message the gnome ever sends, with room to spare. A transport that never
    /// produces a newline must not be able to grow this buffer forever.
    public static let maxMessageBytes = 1024

    public let config: LinkConfig
    private let transport: Transport
    private let clock: Clock
    /// True while the tail of an over-long message is still being discarded.
    private var resynchronising = false

    private var buffer = Data()
    private var latestStatus: DeviceStatus?
    private var latestStatusAt: TimeInterval?
    private var lastHeartbeat: TimeInterval?

    public private(set) var lastAck: DeviceAck?
    public private(set) var refusals: [String: Int] = [:]
    public private(set) var malformedMessages = 0
    public var bufferedBytes: Int { buffer.count }
    public var isConnected: Bool { transport.isConnected }

    /// - Parameter clock: the same clock everything else in the app runs on. This class
    ///   used to read `ProcessInfo.systemUptime` directly when stamping an arriving status,
    ///   while `status(asOf:)` was asked about an uptime that came from `SteadyClock`. The
    ///   two agree right up until the moment `SteadyClock` compensates for a rewind, and
    ///   then they never agree again: every status, however fresh, reads as older than
    ///   `maxStatusAge` and is withheld forever. One clock glitch anywhere in the process's
    ///   life and the gnome silently stops being able to fire, with nothing logged and
    ///   every test still green. Measured: five out of five statuses rejected, each of them
    ///   zero seconds old.
    public init(transport: Transport, clock: Clock, config: LinkConfig = LinkConfig()) {
        self.transport = transport
        self.clock = clock
        self.config = config

        transport.onReceive = { [weak self] data in
            self?.absorb(data)
        }
        transport.onConnectionChange = { [weak self] connected in
            guard let self else { return }
            if !connected {
                // A link that has dropped cannot vouch for anything it said earlier.
                self.latestStatus = nil
                self.latestStatusAt = nil
                self.buffer.removeAll(keepingCapacity: true)
                self.resynchronising = false
            }
            self.lastHeartbeat = nil
        }
    }

    /// Call once per cycle. Sends the heartbeat when one is due.
    public func tick(uptime: TimeInterval) {
        guard transport.isConnected else { return }
        if let last = lastHeartbeat, uptime - last < config.heartbeatInterval { return }
        lastHeartbeat = uptime
        try? send(.heartbeat)
    }

    /// The newest status, or nil when it is too old or the link is down.
    public func status(asOf uptime: TimeInterval) -> DeviceStatus? {
        guard transport.isConnected,
              let status = latestStatus,
              let at = latestStatusAt,
              uptime - at <= config.maxStatusAge else { return nil }
        return status
    }

    public func send(_ command: Command) throws {
        // Encoding first, so a command that cannot be represented never reaches the radio
        // and the caller hears about it rather than the gnome silently doing nothing.
        // Framing is the transport's: BLE carries one object per write, serial needs a
        // newline, and the link has no business knowing which it is talking to.
        try transport.send(transport.framing.frame(try command.encoded()))
    }

    private func absorb(_ data: Data) {
        // Bytes arriving while the transport says it is down are not evidence of anything.
        // `status(asOf:)` re-checks the flag, but only the current one, so a transport that
        // forgot to announce a reconnection could otherwise make a status from a previous
        // session look live.
        guard transport.isConnected else {
            buffer.removeAll(keepingCapacity: true)
            return
        }

        buffer.append(data)

        while let newline = buffer.firstIndex(of: 0x0A) {
            let line = buffer[buffer.startIndex..<newline]
            buffer = buffer[buffer.index(after: newline)...]

            if resynchronising {
                // That newline ended the over-long message, not a real one.
                resynchronising = false
                continue
            }
            handle(Data(line))
        }

        if buffer.count > ActuatorLink.maxMessageBytes {
            // No terminator in a message this long means the stream is out of step. The
            // buffer used to keep its tail, on the theory that it gave the next real
            // message a clean start; measured, it did the opposite — the tail merged with
            // the next message and swallowed that one too, so a single overrun cost two
            // messages rather than one. Everything up to the next newline is discarded
            // instead.
            buffer.removeAll(keepingCapacity: true)
            resynchronising = true
            malformedMessages += 1
        }
    }

    private func handle(_ line: Data) {
        guard !line.isEmpty else { return }
        guard let message = try? IncomingMessage.decode(line) else {
            malformedMessages += 1
            return
        }

        switch message {
        case .status(let status):
            latestStatus = status
            latestStatusAt = clock.uptime
        case .ack(let ack):
            lastAck = ack
            if !ack.ok, let why = ack.why {
                refusals[why, default: 0] += 1
            }
        }
    }
}
