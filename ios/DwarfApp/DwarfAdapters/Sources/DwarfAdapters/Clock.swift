import Foundation

/// The two clocks the pipeline runs on, kept apart on purpose.
public protocol Clock: AnyObject {
    /// Monotonic seconds. Every interval `DwarfCore` measures is on this one.
    var uptime: TimeInterval { get }
    /// Wall clock. Used for the active-hours window and nothing else, so daylight saving
    /// cannot reach a cooldown.
    var now: Date { get }
}

public final class SystemClock: Clock {
    public init() {}

    /// `systemUptime` is unaffected by the wall clock being set, which `Date` is not. It
    /// does not advance while the device is asleep — for a gnome that is plugged in with
    /// the idle timer disabled that should never happen, and `SteadyClock` is what catches
    /// it when it does anyway.
    public var uptime: TimeInterval { ProcessInfo.processInfo.systemUptime }
    public var now: Date { Date() }
}

public final class TestClock: Clock {
    public var uptime: TimeInterval = 0
    public var now: Date = Date(timeIntervalSince1970: 1_780_000_000)
    public init() {}
}

/// A clock that will not go backwards, whatever it is wrapping.
///
/// `DwarfCore` documents that a misbehaving uptime "fails safe", but only because the app is
/// trusted to supply a good one. This is where that trust is made real. A rewind is carried
/// forward as an offset rather than frozen: holding the last value would stop time, and a
/// cooldown that never expires is as broken as one that expires instantly, just quieter.
public final class SteadyClock: Clock {
    private let wrapped: Clock
    private var offset: TimeInterval = 0
    private var lastRaw: TimeInterval?
    private var lastReported: TimeInterval = 0
    /// Reading this clock mutates it, and the app has at least two queues that want the
    /// time: the camera's and the radio's. ThreadSanitizer found twenty-one races here
    /// under eight threads, and the visible damage was worse than torn reads — racing
    /// readers mistake each other's progress for a rewind, so the anomaly counter climbs
    /// and the offset inflates for no reason at all.
    private let lock = NSLock()

    /// How many times the underlying clock misbehaved. Surfaced in the status screen,
    /// because a phone whose clock jumps is a phone with a bigger problem.
    public private(set) var anomalies = 0
    /// The largest single step backwards seen, in seconds.
    public private(set) var worstRewind: TimeInterval = 0

    public init(wrapping clock: Clock) {
        self.wrapped = clock
    }

    public var uptime: TimeInterval {
        lock.lock()
        defer { lock.unlock() }
        let raw = wrapped.uptime

        guard raw.isFinite else {
            anomalies += 1
            return lastReported
        }

        if let last = lastRaw, raw < last {
            let rewind = last - raw
            anomalies += 1
            worstRewind = max(worstRewind, rewind)
            offset += rewind
        }

        lastRaw = raw
        lastReported = raw + offset
        return lastReported
    }

    public var now: Date { wrapped.now }
}
