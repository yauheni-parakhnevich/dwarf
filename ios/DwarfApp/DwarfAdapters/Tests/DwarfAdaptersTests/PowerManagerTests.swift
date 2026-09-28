import XCTest
@testable import DwarfAdapters

final class PowerManagerTests: XCTestCase {
    private func manager() -> (PowerManager, FakeBattery) {
        let battery = FakeBattery()
        return (PowerManager(battery: battery), battery)
    }

    func testTheChargerTurnsOnLowAndOffHigh() {
        let (power, battery) = manager()

        battery.level = 0.35
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 0).charger, true)

        battery.level = 0.60
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 1).charger, true,
                       "still charging between the thresholds")

        battery.level = 0.85
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 2).charger, false)

        battery.level = 0.60
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 3).charger, false,
                       "hysteresis: coming down from full, it stays off until 40%")
    }

    func testAnUnknownBatteryLevelChargesRatherThanGuesses() {
        // UIDevice reports -1 when monitoring is off or the reading is unavailable. A gnome
        // that stops charging because it cannot read its own battery is a gnome that dies
        // overnight.
        let (power, battery) = manager()
        battery.level = -1
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 0).charger, true)
    }

    func testSeriousHeatHalvesTheRateAndStartsTheFan() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .serious, meanLuma: 120, uptime: 0)

        XCTAssertEqual(decision.cycleDivisor, 2)
        XCTAssertTrue(decision.fan)
        XCTAssertFalse(decision.pauseDetection)
    }

    func testCriticalHeatStopsEverything() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .critical, meanLuma: 120, uptime: 0)

        XCTAssertTrue(decision.pauseDetection)
        XCTAssertTrue(decision.disarm)
        XCTAssertTrue(decision.fan)
    }

    func testDarknessPausesOnlyAfterItHasLasted() {
        // A cloud, or a cat walking over the lens, is not nightfall.
        let (power, _) = manager()

        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0).pauseDetection)
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 30).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)
    }

    func testLightHasToLastToUndoDarkness() {
        let (power, _) = manager()
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)

        // A car's headlights sweeping the garden must not restart detection.
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 62).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 100).pauseDetection)
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 123).pauseDetection)
    }

    func testAFlickerDoesNotResetTheDarknessTimer() {
        let (power, _) = manager()
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0)
        _ = power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 30)
        // The light was brief, so darkness starts counting again from 30, not from 0.
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 91).pauseDetection)
    }

    func testASingleBrightFrameOnlyRestartsTheCount() {
        // A flicker must restart the clock from the flicker, not erase the progress and
        // then start again from the next dark reading. Erasing it pushed a dusk that began
        // at 0 with one bright frame at 45 out to 106 seconds instead of 91.
        let (power, _) = manager()
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0)
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 30)
        _ = power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 45)   // the flicker

        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 100).pauseDetection,
                       "55 s after the flicker is not yet dusk")
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 106).pauseDetection,
                      "61 s after the flicker is")
    }

    func testAnUnusableLumaIsReportedAsWellAsObeyed() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .nominal, meanLuma: .nan, uptime: 0)
        XCTAssertTrue(decision.lumaUnusable)
        XCTAssertFalse(decision.pauseDetection, "it still has to last before it counts")

        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: .nan, uptime: 61).pauseDetection)
    }

    func testTheGnomesOwnThermometerIsBelievedBeforeThePhonesIs() {
        // M0 ran ten minutes at full inference load and iOS never left nominal, while the
        // phone was warm to the touch. In open air that is fine; sealed in a gnome in the
        // sun it is not, and the phone is rated to 35 C ambient.
        let (power, _) = manager()

        let warm = power.evaluate(thermal: .nominal, meanLuma: 120, ambientC: 33, uptime: 0)
        XCTAssertEqual(warm.cycleDivisor, 2, "back off before iOS notices")
        XCTAssertTrue(warm.fan)
        XCTAssertFalse(warm.pauseDetection)

        let hot = power.evaluate(thermal: .nominal, meanLuma: 120, ambientC: 37, uptime: 1)
        XCTAssertTrue(hot.pauseDetection)
        XCTAssertTrue(hot.disarm)
        XCTAssertFalse(hot.charger, "charging a phone that is already too hot is the wrong way round")
    }

    func testNoAmbientReadingFallsBackToThePhone() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .nominal, meanLuma: 120, ambientC: nil, uptime: 0)
        XCTAssertEqual(decision.cycleDivisor, 1)
        XCTAssertFalse(decision.pauseDetection)

        // A failed probe reports a sentinel the firmware turns into a fault; if a
        // non-finite value ever reached here it must not read as cold.
        let broken = power.evaluate(thermal: .nominal, meanLuma: 120, ambientC: .nan, uptime: 1)
        XCTAssertEqual(broken.cycleDivisor, 1)
    }
}

