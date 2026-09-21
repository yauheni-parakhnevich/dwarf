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

    ControllerConfig cfg_;
    Shooter shooter_;
    bool armed_ = false;
    bool charge_ = true;   // fail-safe default: the phone must be able to boot
    bool fan_ = false;
    bool fanCmd_ = false;
    bool fanAuto_ = false;
    bool tankOk_ = true;
    bool tankLowPending_ = false;
    bool linkUp_ = false;
    Fault fault_ = Fault::None;
    float pan_ = 0.0f;
    float tilt_ = 0.0f;
    float targetPan_ = 0.0f;
    float targetTilt_ = 0.0f;
    float temp_ = 0.0f;
    Millis lastCmd_ = 0;
    Millis lastUpdate_ = 0;
    Millis tankLowSince_ = 0;
    bool started_ = false;  // guards the first update() call's slew dt
};

}  // namespace dwarf
