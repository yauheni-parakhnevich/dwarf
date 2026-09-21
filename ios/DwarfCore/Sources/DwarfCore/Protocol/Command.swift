import Foundation

/// A message from the phone to the ESP32. See spec §7.
///
/// `Equatable` here is the compiler-synthesised default: exact `Double` equality
/// on every associated value, with no tolerance. `.aim(pan: 0.1 + 0.2, tilt: 0)`
/// is NOT equal to `.aim(pan: 0.3, tilt: 0)`, because `0.1 + 0.2` and `0.3` are
/// different `Double` bit patterns. `Command` is therefore unsuitable as a
/// dictionary key, or as the basis of a "has this changed" cache, whenever the
/// angles involved are computed rather than literal. A caller that needs change
/// detection over computed angles should compare the decision that produced the
/// command, not the encoded `Command` itself.
public enum Command: Equatable, Sendable {
    case heartbeat
    case arm(Bool)
    case aim(pan: Double, tilt: Double)
    case park
    case shoot(pan: Double, tilt: Double, ms: UInt16)
    case charge(Bool)
    case fan(Bool)
    case config(panMin: Double, panMax: Double, tiltMin: Double, tiltMax: Double)

    /// The firmware's hard cap on burst length: mirrors `ShooterConfig::maxBurstMs`
    /// in `firmware/lib/dwarf/shooter.h` (currently 500). `Shooter::request` does
    /// not reject a longer request there -- it silently clamps `ms` down to this
    /// cap (`burstMs_ = (ms > cfg_.maxBurstMs) ? cfg_.maxBurstMs : ms;`) and its
    /// `ack` never reports that the clamp happened. Rejecting an over-long burst
    /// here instead, loudly, in Swift, is better than a phone that thinks it asked
    /// for a 40-second burst and a gnome that quietly fired for half a second. If
    /// the firmware's cap is ever raised, this constant must be raised with it, or
    /// this file will start rejecting requests the firmware would now honour.
    public static let maxBurstMs: UInt16 = 500

    /// The spec's welfare ceiling on a single burst, deliberately below the firmware's
    /// cap: 500 ms is what the hardware refuses to exceed, 400 ms is the most water an
    /// animal should ever receive at once. `FirePolicy` already clamps its own `burstMs`
    /// into 200...400, but it is not the only thing that can build a `shoot` — a
    /// calibration test shot and any manual control in the web UI construct one directly,
    /// because calibration is impossible without firing outside the policy. Checking it
    /// here too means the welfare limit holds on every path to the nozzle, not only the
    /// vetted one.
    public static let maxWelfareBurstMs: UInt16 = 400

    public enum EncodingError: Error, Equatable {
        /// An angle was NaN or infinite. The firmware rejects these, and sending one
        /// would mean a silently dropped command.
        case nonFiniteValue(field: String)
        /// A zero-length burst. The firmware rejects it as "bad".
        case zeroBurst
        /// A burst longer than an animal should ever receive. See
        /// `Command.maxWelfareBurstMs` and `Command.maxBurstMs`.
        case burstTooLong(ms: UInt16)
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
            object = ["c": "aim", "pan": round2(pan), "tilt": round2(tilt)]
        case .park:
            object = ["c": "park"]
        case .shoot(let pan, let tilt, let ms):
            try check(pan, "pan")
            try check(tilt, "tilt")
            guard ms > 0 else { throw EncodingError.zeroBurst }
            guard ms <= Command.maxWelfareBurstMs else { throw EncodingError.burstTooLong(ms: ms) }
            // Int, not Double: the firmware requires a JSON integer here.
            object = ["c": "shoot", "pan": round2(pan), "tilt": round2(tilt), "ms": Int(ms)]
        case .charge(let on):
            object = ["c": "charge", "v": on]
        case .fan(let on):
            object = ["c": "fan", "v": on]
        case .config(let panMin, let panMax, let tiltMin, let tiltMax):
            try check(panMin, "panMin")
            try check(panMax, "panMax")
            try check(tiltMin, "tiltMin")
            try check(tiltMax, "tiltMax")
            object = ["c": "cfg", "panMin": round2(panMin), "panMax": round2(panMax),
                      "tiltMin": round2(tiltMin), "tiltMax": round2(tiltMax)]
        }

        return try Command.serialize(object)
    }

    /// Names the offending field in a normal Swift error before a value ever
    /// reaches `object`. See `serialize(_:)` below for the backstop that catches
    /// what this misses.
    private func check(_ value: Double, _ field: String) throws {
        guard value.isFinite else { throw EncodingError.nonFiniteValue(field: field) }
    }

    /// Rounds an angle to two decimal places before it goes on the wire: an order
    /// of magnitude finer than the servo's ~0.27° deadband (see the pulse-width
    /// mapping in `firmware/lib/dwarf/servo.cpp`), so nothing the mechanism can
    /// act on is lost. This also absorbs floating-point drift accumulated
    /// upstream (e.g. a fit that produces `12.499999999999998` instead of
    /// `12.5`) into a single canonical value.
    ///
    /// Measured caveat: this does NOT reliably shrink the wire message.
    /// `JSONSerialization` does not print `Double` using a shortest-round-trip
    /// algorithm; it prints close to full `Double` precision regardless of how
    /// "round" the value is. A rounded value only serialises short when its
    /// hundredths reduce to a power-of-two fraction (`.00`, `.25`, `.50`, `.75` --
    /// 4 of every 100 possible values); every other rounded value -- e.g. `-59.9`
    /// -> `round2` -> still `-59.9` -- still prints as
    /// `-59.899999999999999`. Do not assume rounding here has fixed message size
    /// or made a BLE sniffer log readable; it has not, in the general case.
    private func round2(_ value: Double) -> Double {
        (value * 100).rounded() / 100
    }

    /// The final backstop before a payload reaches `JSONSerialization`.
    ///
    /// Measured on this platform: `JSONSerialization.data(withJSONObject:)` does
    /// NOT turn a non-finite `Double` (NaN, +/-infinity) into a catchable Swift
    /// `Error`. It raises an Objective-C exception -- `NSInvalidArgumentException`,
    /// reason `"Invalid number value (NaN) in JSON write"` -- that unwinds
    /// straight through a Swift `do/catch` and terminates the process:
    ///
    ///     do {
    ///         _ = try JSONSerialization.data(withJSONObject: ["x": Double.nan])
    ///     } catch {
    ///         // never reached -- the process is already gone.
    ///     }
    ///
    /// On a phone sealed inside a gnome, that crash needs the enclosure opened to
    /// recover from.
    ///
    /// The per-field `check(_:_:)` calls in `encoded()` exist to name the
    /// offending field in a normal, informative Swift error, and should stay.
    /// This sweep exists for the case where a *future* command forgets that
    /// check: it walks the finished dictionary and throws
    /// `EncodingError.nonFiniteValue` for any non-finite `Double` it finds, so
    /// the failure mode stays a catchable Swift error -- never a crash -- even
    /// then.
    ///
    /// Do not remove this as "redundant" with the per-field checks. If it
    /// regresses -- e.g. a call site starts calling
    /// `JSONSerialization.data(withJSONObject:)` directly instead of routing
    /// through here -- the failure mode is a process termination, not a failing
    /// test. See `CommandTests.testSerializeSweepCatchesWhatAPerFieldCheckWouldMiss`,
    /// which exercises this function directly (bypassing every per-field check)
    /// to prove it still turns a non-finite value into a thrown error rather than
    /// a crash.
    ///
    /// Deliberately not `private`: it needs to be reachable from the test target
    /// via `@testable import`, since the whole point of the regression test is to
    /// call it directly rather than through a `Command` case that would exercise
    /// its own `check(_:_:)` first. It is not part of the module's public API
    /// (`Command`'s public surface is `encoded()` and the cases/errors above).
    static func serialize(_ object: [String: Any]) throws -> Data {
        for (key, value) in object {
            if let number = value as? Double, !number.isFinite {
                throw EncodingError.nonFiniteValue(field: key)
            }
        }
        return try JSONSerialization.data(withJSONObject: object, options: [])
    }
}
