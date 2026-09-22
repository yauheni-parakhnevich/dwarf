import Foundation

/// The phone's battery, behind a protocol because `UIDevice` does not exist on a Mac.
public protocol BatteryReader: AnyObject {
    /// 0…1, or a negative number when the level is not available.
    var level: Float { get }
}

public final class FakeBattery: BatteryReader {
    public var level: Float = 0.5
    public init() {}
}

public struct PowerDecision: Equatable, Sendable {
    /// Whether the gnome should be charging the phone.
    public let charger: Bool
    public let fan: Bool
    /// Run one cycle in this many. 1 is full rate.
    public let cycleDivisor: Int
    public let pauseDetection: Bool
    /// Critical heat: stop asking for water at all, not merely stop looking.
    public let disarm: Bool
    /// The frame's mean luma was not a number. Treated as darkness, which is the safe
    /// direction — a broken exposure pipeline should stop the gnome rather than have it
    /// fire blind — but reported separately, because otherwise a permanently NaN luma is
    /// indistinguishable from a long winter night and disables the gnome with nothing to
    /// show for it.
    public let lumaUnusable: Bool
}

public struct PowerLimits: Equatable, Sendable {
    public var chargeBelow: Float = 0.40
    public var stopChargingAbove: Float = 0.80
    public var darkLuma: Double = 40
    /// How long darkness, or light, has to last before it is believed. A cloud is not
    /// nightfall and a car's headlights are not dawn.
    public var lightSettleTime: TimeInterval = 60

    public init() {}
}

/// Battery, heat and daylight. Three rules that all end in doing less.
public final class PowerManager {
    public var limits: PowerLimits
    private let battery: BatteryReader

    private var charging = true
    private var isDark = false
    /// When the luma last crossed the threshold in the direction it is currently heading.
    private var crossedAt: TimeInterval?

    public init(battery: BatteryReader, limits: PowerLimits = PowerLimits()) {
        self.battery = battery
        self.limits = limits
    }

    public func evaluate(thermal: ProcessInfo.ThermalState, meanLuma: Double,
                         uptime: TimeInterval) -> PowerDecision {
        PowerDecision(charger: shouldCharge(),
                      fan: thermal.rawValue >= ProcessInfo.ThermalState.serious.rawValue,
                      cycleDivisor: thermal == .serious ? 2 : 1,
                      pauseDetection: thermal == .critical || darkness(meanLuma, uptime),
                      disarm: thermal == .critical,
                      lumaUnusable: !meanLuma.isFinite)
    }

    private func shouldCharge() -> Bool {
        let level = battery.level
        // A negative reading means the level is unavailable, not that it is empty. Charging
        // a full phone wastes a little heat; refusing to charge a flat one ends the night.
        guard level >= 0 else { return true }

        if charging, level >= limits.stopChargingAbove {
            charging = false
        } else if !charging, level <= limits.chargeBelow {
            charging = true
        }
        return charging
    }

    private func darkness(_ meanLuma: Double, _ uptime: TimeInterval) -> Bool {
        let looksDark = meanLuma.isFinite ? meanLuma < limits.darkLuma : true

        guard looksDark != isDark else {
            // Back on the side it was already on, so whatever crossing was being timed is
            // over — but the clock for the *next* one starts here, not from nothing. This
            // line used to clear the reference entirely, which meant a single bright frame
            // in the middle of a darkening did not merely restart the count, it erased all
            // progress and then began again from the next dark reading: a flicker at 45 s
            // pushed dusk out to 106 s instead of 91 s. Stamping the moment is what the
            // comment in the test always described.
            crossedAt = uptime
            return isDark
        }

        guard let since = crossedAt else {
            crossedAt = uptime
            return isDark
        }

        if uptime - since >= limits.lightSettleTime {
            isDark = looksDark
            crossedAt = nil
        }
        return isDark
    }
}
