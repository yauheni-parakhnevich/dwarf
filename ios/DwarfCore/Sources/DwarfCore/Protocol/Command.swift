import Foundation

/// A message from the phone to the ESP32. See spec §7.
public enum Command: Equatable, Sendable {
    case heartbeat
    case arm(Bool)
    case aim(pan: Double, tilt: Double)
    case park
    case shoot(pan: Double, tilt: Double, ms: UInt16)
    case charge(Bool)
    case fan(Bool)
    case config(panMin: Double, panMax: Double, tiltMin: Double, tiltMax: Double)

    public enum EncodingError: Error, Equatable {
        /// An angle was NaN or infinite. The firmware rejects these, and sending one
        /// would mean a silently dropped command.
        case nonFiniteValue(field: String)
        /// A zero-length burst. The firmware rejects it as "bad".
        case zeroBurst
    }

    public func encoded() throws -> Data {
        var object: [String: Any]

        switch self {
        case .heartbeat:
            object = ["c": "hb"]
        case .arm(let on):
            object = ["c": "arm", "v": on]
        case .aim(let pan, let tilt):
            try check(pan, "pan")
            try check(tilt, "tilt")
            object = ["c": "aim", "pan": pan, "tilt": tilt]
        case .park:
            object = ["c": "park"]
        case .shoot(let pan, let tilt, let ms):
            try check(pan, "pan")
            try check(tilt, "tilt")
            guard ms > 0 else { throw EncodingError.zeroBurst }
            // Int, not Double: the firmware requires a JSON integer here.
            object = ["c": "shoot", "pan": pan, "tilt": tilt, "ms": Int(ms)]
        case .charge(let on):
            object = ["c": "charge", "v": on]
        case .fan(let on):
            object = ["c": "fan", "v": on]
        case .config(let panMin, let panMax, let tiltMin, let tiltMax):
            try check(panMin, "panMin")
            try check(panMax, "panMax")
            try check(tiltMin, "tiltMin")
            try check(tiltMax, "tiltMax")
            object = ["c": "cfg", "panMin": panMin, "panMax": panMax,
                      "tiltMin": tiltMin, "tiltMax": tiltMax]
        }

        return try JSONSerialization.data(withJSONObject: object, options: [])
    }

    private func check(_ value: Double, _ field: String) throws {
        guard value.isFinite else { throw EncodingError.nonFiniteValue(field: field) }
    }
}
