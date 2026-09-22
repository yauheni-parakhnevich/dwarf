import UIKit
import DwarfAdapters

/// `UIDevice` behind the protocol `PowerManager` expects.
public final class DeviceBattery: BatteryReader {
    public init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
    }

    /// -1 when the level is not available, which `PowerManager` reads as "charge anyway".
    public var level: Float { UIDevice.current.batteryLevel }
}
