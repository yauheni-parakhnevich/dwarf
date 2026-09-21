#pragma once
#include "protocol.h"
#include "servo.h"
#include "shooter.h"
#include "types.h"

namespace dwarf {

struct ControllerConfig {
    Limits limits{};
    Millis heartbeatTimeoutMs = 3000;  // link considered dead after this silence
    float slewDegPerSec = 120.0f;
    Millis tankDebounceMs = 2000;      // a sloshing float switch must not trip a fault
    float fanOnC = 40.0f;
    float fanOffC = 35.0f;
    float overtempC = 60.0f;
    float overtempClearC = 55.0f;
    ShooterConfig shooter{};
};

struct Ack {
    bool present = false;
    const char* cmd = "";
    bool ok = false;
    const char* why = nullptr;
};

class Controller {
  public:
    explicit Controller(ControllerConfig cfg = ControllerConfig{})
        : cfg_(cfg), shooter_(cfg.shooter) {}

    // Applies one command and returns the acknowledgement to notify, if any.
    Ack handle(const Command& c, Millis now);

    // Advances time: tank debounce, faults, heartbeat, servo slew, shot machine.
    // tankSwitchClosed is true while the float switch reports water.
    void update(Millis now, bool tankSwitchClosed, float tempC);

    // Performs exactly what the heartbeat-loss path does -- disarm, abort the
    // shot, park the target, charger on -- but does NOT touch the phone
    // heartbeat bookkeeping (lastCmd_/linkUp_). Call this for any LOCAL safety
    // action (a synthesised command through handle() would look like real
    // phone traffic and could mask genuine silence forever). This is also
    // what a BLE onDisconnect callback should call, so a known disconnect is
    // handled at once instead of waiting out the full heartbeat timeout.
    void forceSafe(Millis now);

    // Called when a hardware interrupt has force-closed the valve GPIO
    // because the main loop stalled mid-burst. Aborts the shot through the
    // shooter (so an open burst is counted and the cooldown starts from
    // `now`), disarms, and latches a sticky Fault::ValveTimeout that
    // outranks every other fault and does NOT clear on its own -- only an
    // explicit {"c":"arm","v":false} from the phone (the operator
    // acknowledging the fault) clears it. Recovery is: disarm, then re-arm.
    void notifyValveForceClosed(Millis now);

    Status status() const;

    bool armed() const { return armed_; }
    bool valveOpen() const { return shooter_.valveOpen(); }
    bool pumpOn() const { return armed_ && tankOk_ && fault_ == Fault::None; }
    bool chargeOn() const { return charge_; }
    bool fanOn() const { return fan_; }
    float pan() const { return pan_; }
    float tilt() const { return tilt_; }
    Fault fault() const { return fault_; }
    ShooterState shooterState() const { return shooter_.state(); }

  private:
    void enterSafeState(Millis now);

    // Overtemp and TankEmpty share the same "raise" action: latch the fault,
    // disarm, and abort whatever the shooter is doing -- spraying, or trying
    // to, is never safe once either of these is true.
    void latchDisarmingFault(Fault f, Millis now);

    ControllerConfig cfg_;
    Shooter shooter_;
    bool armed_ = false;
    bool charge_ = true;   // fail-safe default: the phone must be able to boot
    bool fan_ = false;
    bool fanCmd_ = false;
    bool fanAuto_ = false;
    bool tankOk_ = true;
    // The raw float-switch reading currently being debounced, and how long it
    // has read that way contiguously. Both edges use the same tankDebounceMs:
    // a single spurious sample, in either direction, must change nothing.
    bool tankPendingClosed_ = true;
    Millis tankPendingSince_ = 0;
    bool linkUp_ = false;
    Fault fault_ = Fault::None;
    bool valveTimeoutLatched_ = false;
    float pan_ = 0.0f;
    float tilt_ = 0.0f;
    float targetPan_ = 0.0f;
    float targetTilt_ = 0.0f;
    float temp_ = 0.0f;
    Millis lastCmd_ = 0;
    Millis lastUpdate_ = 0;
    bool started_ = false;  // guards the first update() call's slew dt
};

}  // namespace dwarf
