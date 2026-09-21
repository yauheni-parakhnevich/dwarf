import XCTest
@testable import DwarfCore

final class FirePolicyTests: XCTestCase {
    /// Midday, well inside the active window.
    private func noon() -> Date {
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15
        components.hour = 12; components.minute = 0
        return Calendar.current.date(from: components)!
    }

    private func night() -> Date {
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15
        components.hour = 23; components.minute = 30
        return Calendar.current.date(from: components)!
    }

    private func track(id: Int = 1, x: Double = 0.5, y: Double = 0.7,
                       confirmed: Bool = true, still: Bool = true,
                       ambiguous: Bool = false) -> Track {
        Track(id: id,
              box: Rect(x: x - 0.04, y: y - 0.06, width: 0.08, height: 0.06),
              confidence: 0.9, lastSeen: 0, isConfirmed: confirmed, isStill: still,
              isAmbiguous: ambiguous)
    }

    private func healthyStatus() -> DeviceStatus {
        DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: true, pump: true,
                     charge: false, fan: false, temp: 22, fault: nil, shots: 0)
    }

    private func solution(range: Double = 5, flagged: Bool = false) -> AimSolution {
        AimSolution(pan: 12, tilt: 4, rangeM: range,
                    target: range >= 4 ? .head : .body,
                    isFlagged: flagged, flagReason: flagged ? "test" : nil,
                    flagReasons: flagged ? ["test"] : [])
    }

    private func input(mode: Mode = .live, tracks: [Track]? = nil,
                       masks: MaskSet = .empty, status: DeviceStatus? = nil,
                       luma: Double = 120, now: Date? = nil, uptime: TimeInterval = 100,
                       range: Double = 5, flagged: Bool = false) -> PolicyInput {
        let resolvedTracks = tracks ?? [track()]
        return PolicyInput(
            mode: mode,
            tracks: resolvedTracks,
            solutions: Dictionary(uniqueKeysWithValues:
                resolvedTracks.map { ($0.id, solution(range: range, flagged: flagged)) }),
            masks: masks,
            status: status ?? healthyStatus(),
            meanLuma: luma,
            now: now ?? noon(),
            uptime: uptime
        )
    }

    // MARK: firing

    func testFiresWhenEverythingIsSatisfied() {
        let policy = FirePolicy()
        guard case .shoot(let pan, let tilt, let ms) = policy.decide(input()) else {
            return XCTFail("expected a shot")
        }
        XCTAssertEqual(pan, 12, accuracy: 1e-9)
        XCTAssertEqual(tilt, 4, accuracy: 1e-9)
        XCTAssertEqual(ms, 300)
    }

    func testDryRunReportsWithoutFiring() {
        let policy = FirePolicy()
        guard case .wouldShoot = policy.decide(input(mode: .dryRun)) else {
            return XCTFail("expected a logged would-shoot")
        }
    }

    func testDisarmedModeDoesNothing() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(mode: .disarmed)), .none)
    }

    // MARK: the track itself

    func testAnUnconfirmedTrackIsOnlyTracked() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)])) else {
            return XCTFail("expected the head to follow but not fire")
        }
    }

    func testAMovingTrackIsFollowedNotFired() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(still: false)])) else {
            return XCTFail("expected aim only")
        }
    }

    func testAnAmbiguousTrackIsFollowedNotFired() {
        var ambiguous = track()
        ambiguous.isAmbiguous = true
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [ambiguous])) else {
            return XCTFail("two tangled cats: follow, never fire")
        }
    }

    func testAnIgnoredZoneTrackIsNotEvenFollowed() {
        let zone = MaskSet(ignoreZones: [Polygon(points: [
            Point(x: 0.4, y: 0.6), Point(x: 0.6, y: 0.6),
            Point(x: 0.6, y: 0.8), Point(x: 0.4, y: 0.8)
        ])])
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(masks: zone, uptime: 100)), .none)
    }

    // MARK: welfare limits

    func testTooCloseIsNeverFired() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(range: 1.5)) else {
            return XCTFail("inside 2 m the jet is a hard stream: follow, never fire")
        }
    }

    func testNoFireZoneBlocksTheShot() {
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0.3, y: 0.6), Point(x: 0.7, y: 0.6),
            Point(x: 0.7, y: 0.9), Point(x: 0.3, y: 0.9)
        ])])
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(masks: zone)) else {
            return XCTFail("expected aim only")
        }
    }

    func testAFlaggedSolutionBlocksTheShot() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(flagged: true)) else {
            return XCTFail("expected aim only")
        }
    }

    func testOutsideTheActiveWindowNothingFires() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(now: night())), .none)
    }

    func testDarknessStopsEverything() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(luma: 12)), .none)
    }

    // MARK: cooldowns and caps

    func testTheSameTrackCannotBeShotTwiceInTenSeconds() {
        let policy = FirePolicy()
        guard case .shoot = policy.decide(input(uptime: 100)) else { return XCTFail("first shot") }

        guard case .aim = policy.decide(input(uptime: 105)) else {
            return XCTFail("5 s later must not fire again")
        }
        guard case .shoot = policy.decide(input(uptime: 111)) else {
            return XCTFail("11 s later is allowed")
        }
    }

    func testATrackIsOnlyShotThreeTimes() {
        let policy = FirePolicy()
        var time = 100.0
        for _ in 0..<3 {
            guard case .shoot = policy.decide(input(uptime: time)) else {
                return XCTFail("expected a shot at \(time)")
            }
            time += 11
        }
        guard case .aim = policy.decide(input(uptime: time)) else {
            return XCTFail("the fourth shot at one cat is harassment, not deterrence")
        }
    }

    func testTheHourlyCapAppliesAcrossTracks() {
        var limits = FireLimits()
        limits.maxShotsPerHour = 2
        let policy = FirePolicy(limits: limits)
        var time = 100.0

        for id in 1...2 {
            guard case .shoot = policy.decide(PolicyInput(
                mode: .live, tracks: [track(id: id)], solutions: [id: solution()],
                masks: .empty, status: healthyStatus(), meanLuma: 120,
                now: noon(), uptime: time)) else { return XCTFail("shot \(id)") }
            time += 11
        }

        guard case .aim = policy.decide(PolicyInput(
            mode: .live, tracks: [track(id: 3)], solutions: [3: solution()],
            masks: .empty, status: healthyStatus(), meanLuma: 120,
            now: noon(), uptime: time)) else { return XCTFail("cap should hold") }
    }

    func testTheHourlyCapExpires() {
        var limits = FireLimits()
        limits.maxShotsPerHour = 1
        let policy = FirePolicy(limits: limits)

        guard case .shoot = policy.decide(input(uptime: 100)) else { return XCTFail("first") }
        guard case .aim = policy.decide(input(tracks: [track(id: 2)],
                                              uptime: 200)) else { return XCTFail("still capped") }
        guard case .shoot = policy.decide(PolicyInput(
            mode: .live, tracks: [track(id: 2)], solutions: [2: solution()],
            masks: .empty, status: healthyStatus(), meanLuma: 120,
            now: noon(), uptime: 100 + 3601)) else { return XCTFail("an hour later is fine") }
    }

    // MARK: the device's own state

    func testADisarmedDeviceIsNotFiredAt() {
        let status = DeviceStatus(armed: false, pan: 0, tilt: 0, tankOk: true, pump: false,
                                  charge: true, fan: false, temp: 22, fault: nil, shots: 0)
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(status: status)) else { return XCTFail("expected aim") }
    }

    func testAnEmptyTankBlocksTheShot() {
        let status = DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: false, pump: false,
                                  charge: true, fan: false, temp: 22, fault: .tankEmpty, shots: 0)
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(status: status)) else { return XCTFail("expected aim") }
    }

    func testAMissingStatusBlocksTheShot() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(PolicyInput(
            mode: .live, tracks: [track()], solutions: [1: solution()], masks: .empty,
            status: nil, meanLuma: 120, now: noon(), uptime: 100)) else {
            return XCTFail("no status means no idea whether it is safe to fire")
        }
    }

    // MARK: following and parking

    func testAimIsThrottled() {
        let policy = FirePolicy()
        // An unconfirmed track is followed but never fired at, which isolates aiming.
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("first aim")
        }
        XCTAssertEqual(policy.decide(input(tracks: [track(confirmed: false)], uptime: 100.1)), .none,
                       "aim at 5 Hz, not at frame rate")
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100.3)) else {
            return XCTFail("after the throttle interval, aim again")
        }
    }

    func testTheHeadParksAfterTheCatLeaves() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("aim")
        }
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 105)), .none)
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 111)), .park)
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 112)), .none,
                       "park once, not repeatedly")
    }
}
