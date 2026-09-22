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
        /// A numeric field held a value `UInt32(_:)` cannot represent -- negative,
        /// non-finite, or larger than `UInt32.max`. Thrown deliberately, because
        /// `UInt32(_:)` does not throw on such a value: it hits a fatal-error trap and
        /// takes the whole process down with it. That is the same crash class
        /// `Command.serialize` exists to prevent on the outgoing side (see
        /// `Command.swift`'s doc comment on non-finite angles reaching
        /// `JSONSerialization`); this is its incoming twin -- a corrupted BLE
        /// notification that still parses as JSON must not be able to kill the app.
        ///
        /// If the validation that throws this ever regresses -- e.g. a future field
        /// goes back to a bare `UInt32(try number(...))` -- the symptom is NOT a red
        /// test. It is the app dying outright, silently, the instant a single garbled
        /// packet arrives, the same way the encoder used to die on a NaN angle.
        case outOfRange(field: String, value: Double)
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
        // Narrows a field to `UInt32` without ever handing `UInt32(_:)` a value it cannot
        // represent -- see `DecodingError.outOfRange`. A fractional value (e.g. a
        // corrupted `3.7`) is truncated toward zero deliberately, the same truncation
        // `UInt32(_:)` itself performs for an in-range fractional value; only a value
        // that is negative, non-finite (including the NaN `number(_:)` produces for a
        // JSON `null`), or too large to fit is rejected.
        func counter(_ key: String) throws -> UInt32 {
            let value = try number(key)
            guard value.isFinite, value >= 0, value <= Double(UInt32.max) else {
                throw DecodingError.outOfRange(field: key, value: value)
            }
            return UInt32(value)
        }

        guard let tank = object["tank"] as? String else { throw DecodingError.missingField("tank") }

        let faultCode = object["fault"] as? String   // JSON null decodes to NSNull, not String

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
            shots: try counter("shots")
        ))
    }
}
