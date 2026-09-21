import Foundation

/// A latched fault reported by the ESP32.
public enum DeviceFault: Equatable, Sendable {
    case tankEmpty
    case overtemp
    case tempSensor
    case valveTimeout
    /// A code this build does not know. Kept rather than discarded so a firmware newer
    /// than the app still shows something useful instead of looking healthy.
    case unknown(String)

    public init(code: String) {
        switch code {
        case "TANK_EMPTY": self = .tankEmpty
        case "OVERTEMP": self = .overtemp
        case "TEMP_SENSOR": self = .tempSensor
        case "VALVE_TIMEOUT": self = .valveTimeout
        default: self = .unknown(code)
        }
    }
}

/// The device state the ESP32 notifies about once a second and on every change.
public struct DeviceStatus: Equatable, Sendable {
    public let armed: Bool
    public let pan: Double
    public let tilt: Double
    public let tankOk: Bool
    public let pump: Bool
    public let charge: Bool
    public let fan: Bool
    public let temp: Double
    public let fault: DeviceFault?
    public let shots: UInt32

    /// Whether the device is in a state where a shot could be accepted at all. The full
    /// decision lives in FirePolicy; this is just the device's half of it.
    public var canFire: Bool { armed && tankOk && fault == nil }
}

/// The reply to a command. `why` is present only when `ok` is false.
public struct DeviceAck: Equatable, Sendable {
    public let command: String
    public let ok: Bool
    public let why: String?
}

public enum IncomingMessage: Equatable, Sendable {
    case status(DeviceStatus)
    case ack(DeviceAck)

    public enum DecodingError: Error, Equatable {
        case notAnObject
        case unrecognised
        case missingField(String)
    }

    public static func decode(_ data: Data) throws -> IncomingMessage {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw DecodingError.notAnObject
        }

        if let command = object["ack"] as? String {
            guard let ok = object["ok"] as? Bool else { throw DecodingError.missingField("ok") }
            return .ack(DeviceAck(command: command, ok: ok, why: object["why"] as? String))
        }

        guard object["armed"] != nil else { throw DecodingError.unrecognised }

        // `formatStatus` on the device (firmware/lib/dwarf/protocol.cpp) rounds pan, tilt
        // and temp through a helper that serialises a non-finite float (NaN or +/-infinity)
        // as JSON `null` rather than a number -- ArduinoJson has no other way to emit a
        // non-finite float, since JSON itself has no token for one. That is not a
        // hypothetical: the `temp_sensor` fixture in protocol/fixtures/status.json is a
        // real "dead probe" status with `"temp":null`, produced by a firmware test that
        // sets `s.temp = quiet_NaN()`. Treating `null` here as `Double.nan` -- rather than
        // as a missing field -- is what lets that legitimate, firmware-emitted message
        // decode instead of being rejected as malformed. `shots` never goes through that
        // rounding helper (it is serialised straight from a uint32_t), so a null there
        // would mean something is actually wrong; NaN is an honest way to surface that
        // through the same code path rather than adding a separate case for it.
        func number(_ key: String) throws -> Double {
            if object[key] is NSNull { return .nan }
            guard let value = object[key] as? NSNumber else { throw DecodingError.missingField(key) }
            return value.doubleValue
        }
        func flag(_ key: String) throws -> Bool {
            guard let value = object[key] as? Bool else { throw DecodingError.missingField(key) }
            return value
        }

        guard let tank = object["tank"] as? String else { throw DecodingError.missingField("tank") }

        let faultCode = object["fault"] as? String   // JSON null decodes to NSNull, not String

        let shotsValue = try number("shots")
        // A garbled or malicious "shots" (negative, fractional, out of UInt32 range, or the
        // NaN case discussed above) would trap `UInt32(_:)` rather than throw a catchable
        // error. The firmware never sends such a value, so this is left as a known, narrow
        // gap rather than papered over here -- see the accompanying analysis.
        return .status(DeviceStatus(
            armed: try flag("armed"),
            pan: try number("pan"),
            tilt: try number("tilt"),
            tankOk: tank == "ok",
            pump: try flag("pump"),
            charge: try flag("charge"),
            fan: try flag("fan"),
            temp: try number("temp"),
            fault: faultCode.map(DeviceFault.init(code:)),
            shots: UInt32(shotsValue)
        ))
    }
}
