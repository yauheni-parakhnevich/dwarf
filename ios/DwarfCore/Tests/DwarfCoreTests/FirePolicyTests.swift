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

    // MARK: the per-animal budget survives an id change

    func testThreeShotsAtAPlaceThenAnIDChangeThereIsRefused() {
        let policy = FirePolicy()
        var time = 100.0
        for _ in 0..<3 {
            guard case .shoot = policy.decide(input(tracks: [track(id: 1)], uptime: time)) else {
                return XCTFail("expected a shot at \(time)")
            }
            time += 11
        }
        // The tracker drops the track (an occlusion, a detector gap) and mints a new id for
        // the same physical cat, still standing in the same spot.
        guard case .aim = policy.decide(input(tracks: [track(id: 2)], uptime: time)) else {
            return XCTFail("a new id at the same place must not get a fresh budget")
        }
    }

    func testTheSamePlaceGetsAFreshBudgetAfterTheAnimalWindow() {
        let policy = FirePolicy()
        var time = 100.0
        for _ in 0..<3 {
            guard case .shoot = policy.decide(input(tracks: [track(id: 1)], uptime: time)) else {
                return XCTFail("expected a shot at \(time)")
            }
            time += 11
        }
        guard case .aim = policy.decide(input(tracks: [track(id: 2)], uptime: time)) else {
            return XCTFail("still within the animal window")
        }
        let later = 100 + FireLimits().animalWindow + 1
        guard case .shoot = policy.decide(input(tracks: [track(id: 3)], uptime: later)) else {
            return XCTFail("a visit long after the animal window should get a fresh budget")
        }
    }

    func testADifferentAnimalFarAwayIsUnaffected() {
        let policy = FirePolicy()
        var time = 100.0
        for _ in 0..<3 {
            guard case .shoot = policy.decide(input(tracks: [track(id: 1)], uptime: time)) else {
                return XCTFail("expected a shot at \(time)")
            }
            time += 11
        }
        // A different cat, well outside animalRadius (0.15) from the first one's spot.
        guard case .shoot = policy.decide(input(tracks: [track(id: 2, x: 0.05, y: 0.7)], uptime: time)) else {
            return XCTFail("a genuinely different animal must not inherit the first one's spent budget")
        }
    }

    // MARK: parking when the system itself stops operating

    func testDarknessParksTheHeadInsteadOfLeavingItAimed() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("expected aim while tracking")
        }
        XCTAssertEqual(policy.decide(input(tracks: [track(confirmed: false)], now: night(), uptime: 100.3)), .park,
                       "the head should return to centre the moment the system stops operating")
        XCTAssertEqual(policy.decide(input(tracks: [track(confirmed: false)], now: night(), uptime: 100.6)), .none,
                       "park once, not repeatedly")
    }

    func testDisarmingParksTheHeadInsteadOfLeavingItAimed() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("expected aim while tracking")
        }
        XCTAssertEqual(policy.decide(input(mode: .disarmed, tracks: [track(confirmed: false)], uptime: 100.3)), .park)
        XCTAssertEqual(policy.decide(input(mode: .disarmed, tracks: [track(confirmed: false)], uptime: 100.6)), .none)
    }

    // MARK: backing off aiming at a track that cannot be fired at

    func testAStructurallyRefusedTrackBacksOffAfterThirtySeconds() {
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0.3, y: 0.6), Point(x: 0.7, y: 0.6),
            Point(x: 0.7, y: 0.9), Point(x: 0.3, y: 0.9)
        ])])
        let policy = FirePolicy()
        // Confirmed and still -- would otherwise fire -- but standing in a no-fire zone.
        guard case .aim = policy.decide(input(masks: zone, uptime: 100)) else {
            return XCTFail("expected aim before the backoff window elapses")
        }
        guard case .aim = policy.decide(input(masks: zone, uptime: 129)) else {
            return XCTFail("still within the 30 s backoff window")
        }
        XCTAssertEqual(policy.decide(input(masks: zone, uptime: 131)), .park,
                       "30 s of continuous, structural refusal: stop grinding the servo and park")
        XCTAssertEqual(policy.decide(input(masks: zone, uptime: 131.3)), .none,
                       "stay parked, not repeatedly re-parking, while still refused")
    }

    func testAStructuralRefusalClearingResumesAimingImmediately() {
        let policy = FirePolicy()
        // Never eligible to fire (moving), which isolates aiming from firing exactly as the
        // aim-only tests above do.
        let moving = track(still: false)
        guard case .aim = policy.decide(input(tracks: [moving], uptime: 100, flagged: true)) else {
            return XCTFail("expected aim before the backoff window elapses")
        }
        guard case .aim = policy.decide(input(tracks: [moving], uptime: 129, flagged: true)) else {
            return XCTFail("still within the 30 s backoff window")
        }
        XCTAssertEqual(policy.decide(input(tracks: [moving], uptime: 131, flagged: true)), .park,
                       "30 s of a flagged solution: back off")
        // The solution stops being flagged -- the structural refusal clears -- while the cat
        // is still moving, so it still cannot be fired at, only aimed at.
        guard case .aim = policy.decide(input(tracks: [moving], uptime: 131.3, flagged: false)) else {
            return XCTFail("expected aiming to resume immediately once the structural refusal clears")
        }
    }

    func testAMerelyUnconfirmedTrackIsNotBackedOff() {
        let policy = FirePolicy()
        let unconfirmed = track(confirmed: false)
        for time in stride(from: 100.0, through: 140.0, by: 5.0) {
            guard case .aim = policy.decide(input(tracks: [unconfirmed], uptime: time)) else {
                return XCTFail("an unconfirmed track should keep being aimed at, not backed off, t=\(time)")
            }
        }
    }

    // MARK: more than one cat

    /// Two cats a good distance apart, each with its own aim solution, so which one a
    /// decision was about can be read off the pan angle.
    private func twoCats(uptime: TimeInterval, confidences: (Double, Double) = (0.9, 0.9)) -> PolicyInput {
        func cat(id: Int, x: Double, confidence: Double) -> Track {
            Track(id: id, box: Rect(x: x - 0.04, y: 0.64, width: 0.08, height: 0.06),
                  confidence: confidence, lastSeen: uptime,
                  isConfirmed: true, isStill: true, isAmbiguous: false)
        }
        let tracks = [cat(id: 1, x: 0.3, confidence: confidences.0),
                      cat(id: 2, x: 0.7, confidence: confidences.1)]
        return PolicyInput(
            mode: .live,
            tracks: tracks,
            solutions: [1: AimSolution(pan: -20, tilt: 4, rangeM: 5, target: .head,
                                       isFlagged: false, flagReason: nil, flagReasons: []),
                        2: AimSolution(pan: 20, tilt: 4, rangeM: 5, target: .head,
                                       isFlagged: false, flagReason: nil, flagReasons: [])],
            masks: .empty,
            status: healthyStatus(),
            meanLuma: 120,
            now: noon(),
            uptime: uptime
        )
    }

    func testASecondCatIsNotStarvedByTheFirst() {
        // Ranking candidates by confidence alone and only ever acting on the top one let
        // a cat that had already spent its budget keep the head to itself for as long as
        // it stayed in frame — it was merely rate-limited, never structurally unfireable,
        // so every cycle aimed at it again. A second cat sitting a metre away got nothing.
        let policy = FirePolicy()
        var pans: [Double] = []

        for i in 0..<300 {   // 30 s at 10 Hz, both cats sitting still in the open
            if case .shoot(let pan, _, _) = policy.decide(twoCats(uptime: 100 + Double(i) * 0.1)) {
                pans.append(pan)
            }
        }

        XCTAssertTrue(pans.contains { $0 < 0 }, "the first cat was never sprayed: \(pans)")
        XCTAssertTrue(pans.contains { $0 > 0 }, "the second cat was never sprayed: \(pans)")
    }

    func testShotsAreSpacedByWhatTheHardwareCanDo() {
        // One nozzle, and a firmware cooldown that would refuse anything sooner. Two
        // different cats must not produce two shots inside that gap: the second would be
        // bounced by the ESP32 and still spend the animal's budget here.
        let policy = FirePolicy()
        var times: [TimeInterval] = []

        for i in 0..<300 {
            let uptime = 100 + Double(i) * 0.1
            if case .shoot = policy.decide(twoCats(uptime: uptime)) { times.append(uptime) }
        }

        XCTAssertGreaterThanOrEqual(times.count, 2, "expected shots at both cats: \(times)")
        for (earlier, later) in zip(times, times.dropFirst()) {
            XCTAssertGreaterThanOrEqual(later - earlier, FireLimits().minDeviceInterval - 1e-9,
                                        "two shots \(later - earlier) s apart: \(times)")
        }
    }

    func testTheHigherConfidenceCatIsStillPreferredWhenBothCanBeFiredAt() {
        // Preferring a fireable candidate must not throw away the ranking itself.
        let policy = FirePolicy()
        guard case .shoot(let pan, _, _) = policy.decide(twoCats(uptime: 100, confidences: (0.6, 0.95))) else {
            return XCTFail("expected a shot")
        }
        XCTAssertGreaterThan(pan, 0, "the more confident cat should have been chosen")
    }

    // MARK: the welfare envelope

    func testBurstLengthIsClampedIntoTheWelfareRange() {
        // burstMs is a plain setting a screen could bind straight to. The spec's range is
        // 200...400 ms, and neither end is negotiable at the point water leaves the nozzle.
        var tooLong = FireLimits(); tooLong.burstMs = 450
        var tooShort = FireLimits(); tooShort.burstMs = 50

        guard case .shoot(_, _, let longMs) = FirePolicy(limits: tooLong).decide(input()) else {
            return XCTFail("expected a shot")
        }
        guard case .shoot(_, _, let shortMs) = FirePolicy(limits: tooShort).decide(input()) else {
            return XCTFail("expected a shot")
        }
        XCTAssertEqual(longMs, 400)
        XCTAssertEqual(shortMs, 200)
    }

    func testTheMinimumRangeCannotBeLoweredBelowTheHardStreamDistance() {
        // Closer than 2 m the jet is a hard stream. Setting the limit lower must not work.
        var reckless = FireLimits(); reckless.minRangeM = 0.2
        let policy = FirePolicy(limits: reckless)
        XCTAssertEqual(policy.decide(input(range: 1.5)), .aim(pan: 12, tilt: 4))
    }

    func testANonFiniteMinimumRangeFailsSafe() {
        var broken = FireLimits(); broken.minRangeM = .nan
        let policy = FirePolicy(limits: broken)
        XCTAssertEqual(policy.decide(input(range: 1.5)), .aim(pan: 12, tilt: 4))
    }

    func testTheWelfareEnvelopeSurvivesAssigningLimitsLater() {
        let policy = FirePolicy()
        var reckless = FireLimits(); reckless.burstMs = 450; reckless.minRangeM = 0.2
        policy.limits = reckless
        XCTAssertEqual(policy.limits.burstMs, 400)
        XCTAssertEqual(policy.limits.minRangeM, 2)
    }
}
