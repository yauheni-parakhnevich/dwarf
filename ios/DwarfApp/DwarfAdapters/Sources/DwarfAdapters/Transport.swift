import Foundation

/// A pipe that carries bytes to the gnome and back. CoreBluetooth implements this on the
/// phone; the fake below implements it everywhere else.
/// How one message is marked off from the next on a particular pipe.
public enum Framing: Equatable, Sendable {
    /// One message per write, which is what a BLE characteristic gives for free.
    case perWrite
    /// One JSON object per line, which is what the firmware's serial console reads.
    case newlineTerminated

    public func frame(_ data: Data) -> Data {
        switch self {
        case .perWrite: return data
        case .newlineTerminated: return data + Data("\n".utf8)
        }
    }
}

public protocol Transport: AnyObject {
    var isConnected: Bool { get }
    var framing: Framing { get }
    /// Called with whatever arrived, in whatever sized pieces it arrived in.
    var onReceive: ((Data) -> Void)? { get set }
    /// Called when the link comes up or goes down.
    var onConnectionChange: ((Bool) -> Void)? { get set }
    func send(_ data: Data) throws
}

public enum TransportError: Error, Equatable {
    case notConnected
}

public final class FakeTransport: Transport {
    public var isConnected = false
    public var framing: Framing = .perWrite
    public var onReceive: ((Data) -> Void)?
    public var onConnectionChange: ((Bool) -> Void)?

    public private(set) var sent: [Data] = []
    public var sentStrings: [String] { sent.map { String(decoding: $0, as: UTF8.self) } }

    public init() {}

    public func send(_ data: Data) throws {
        guard isConnected else { throw TransportError.notConnected }
        sent.append(data)
    }

    /// Hand bytes to the link as if the radio had delivered them. `at` is the uptime the
    /// link should record them against.
    public func deliver<C: DataProtocol>(_ bytes: C, at uptime: TimeInterval) {
        receivedAt = uptime
        onReceive?(Data(bytes))
    }

    public func setConnected(_ connected: Bool) {
        isConnected = connected
        onConnectionChange?(connected)
    }

    /// Read by `ActuatorLink` in tests so a delivery can be given a timestamp without the
    /// production API growing one it does not need.
    public var receivedAt: TimeInterval = 0
}
