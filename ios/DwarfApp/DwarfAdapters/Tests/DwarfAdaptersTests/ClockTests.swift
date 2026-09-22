import XCTest
@testable import DwarfAdapters

final class ClockTests: XCTestCase {
    func testTheSystemClockMovesForward() {
        let clock = SystemClock()
        let first = clock.uptime
        // Busy-wait rather than sleep: this asserts the clock advances, not that the test
        // runner can nap.
        while clock.uptime == first {}
        XCTAssertGreaterThan(clock.uptime, first)
    }

    func testASteadyClockPassesAWellBehavedClockThrough() {
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 10
        XCTAssertEqual(clock.uptime, 10, accuracy: 1e-9)
        raw.uptime = 11.5
        XCTAssertEqual(clock.uptime, 11.5, accuracy: 1e-9)
        XCTAssertEqual(clock.anomalies, 0)
    }

    func testASteadyClockNeverGoesBackwards() {
        // The failure this exists for: a rewound uptime makes every "how long since" answer
        // negative, so cooldowns look expired and caps look empty. The gnome would fire
        // again immediately.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 100
        _ = clock.uptime
        raw.uptime = 40

        XCTAssertGreaterThanOrEqual(clock.uptime, 100)
        XCTAssertEqual(clock.anomalies, 1)
        XCTAssertEqual(clock.worstRewind, 60, accuracy: 1e-9)
    }

    func testTimeKeepsMovingAfterARewind() {
        // Holding the last value would stop time altogether, and a cooldown that never
        // expires is its own kind of broken. The offset carries on from where it was.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 100
        _ = clock.uptime
        raw.uptime = 0
        let atRewind = clock.uptime
        raw.uptime = 5

        XCTAssertEqual(clock.uptime - atRewind, 5, accuracy: 1e-9)
    }

    func testTheWallClockIsPassedStraightThrough() {
        // now is used for exactly one thing — the active-hours window — and a jump there
        // is a timezone change or daylight saving, which is information, not corruption.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)
        let moment = Date(timeIntervalSince1970: 1_780_000_000)
        raw.now = moment
        XCTAssertEqual(clock.now, moment)
    }

    func testANonFiniteRawUptimeIsRefused() {
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)
        raw.uptime = 50
        _ = clock.uptime
        raw.uptime = .nan

        XCTAssertEqual(clock.uptime, 50, accuracy: 1e-9)
        XCTAssertEqual(clock.anomalies, 1)
    }
}
