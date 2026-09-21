#include "controller.h"

#include <cmath>

namespace dwarf {

namespace {

// True while a shot owns the head: Move (slewing in), Settle (holding still
// before firing) or Open (water actually leaving the nozzle). Re-pointing the
// head during any of these phases is exactly the bug that let a shot land, or
// a valve open, somewhere other than where it was aimed.
bool shooterBusy(ShooterState s) {
    return s == ShooterState::Move || s == ShooterState::Settle || s == ShooterState::Open;
}

// The mechanical envelope of the pan/tilt hardware: a limit outside this is
// physically nonsensical and would drive a servo into a stalled end stop.
// Written as an inclusive "is it inside" test (rather than "is it outside")
// so that a NaN limit -- which compares false against everything -- fails
// this check and is rejected rather than silently sliding through.
bool withinMechanicalEnvelope(float v) { return v >= -90.0f && v <= 90.0f; }

// A live sensor reading must be finite and within the physically possible
// span for the dry-zone. -127 (the DS18B20 "disconnected probe" sentinel) is
// an ordinary finite number, so it fails this range check rather than a
// finiteness check alone.
bool isValidTempReading(float t) {
    return std::isfinite(t) && t >= -40.0f && t <= 125.0f;
}

}  // namespace

Ack Controller::handle(const Command& c, Millis now) {
    Ack ack;
    if (c.type == CmdType::None) {
        ack.present = true;
        ack.cmd = "?";
        ack.ok = false;
        ack.why = "bad";
        return ack;
    }

    lastCmd_ = now;
    linkUp_ = true;

    switch (c.type) {
        case CmdType::Hb:
            break;

        case CmdType::Arm:
            ack.present = true;
            ack.cmd = "arm";
            if (c.flag && fault_ != Fault::None) {
                ack.ok = false;
                ack.why = "fault";
                break;
            }
            // An explicit disarm is the operator acknowledging a latched
            // fault: it is the only thing that clears Fault::ValveTimeout.
            if (!c.flag && valveTimeoutLatched_) {
                valveTimeoutLatched_ = false;
                fault_ = Fault::None;
            }
            armed_ = c.flag;
            if (!armed_) shooter_.abort(now);
            ack.ok = true;
            break;

        case CmdType::Aim:
            // A shot in flight owns the head until it lands: re-pointing it
            // now is exactly how a shot ends up landing, or a valve opening,
            // somewhere other than where it was aimed. aim is unacked by
            // design, so silently dropping it is not a reporting gap.
            if (!shooterBusy(shooter_.state())) {
                targetPan_ = clampf(c.pan, cfg_.limits.panMin, cfg_.limits.panMax);
                targetTilt_ = clampf(c.tilt, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            }
            break;

        case CmdType::Park:
            ack.present = true;
            ack.cmd = "park";
            if (shooterBusy(shooter_.state())) {
                ack.ok = false;
                ack.why = "busy";
                break;
            }
            // Park means "the nominal centre", but cfg is not required to
            // leave 0 inside the configured range: clamp into whatever the
            // current limits actually are, same as every other target.
            targetPan_ = clampf(0.0f, cfg_.limits.panMin, cfg_.limits.panMax);
            targetTilt_ = clampf(0.0f, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            ack.ok = true;
            break;

        case CmdType::Shoot: {
            ack.present = true;
            ack.cmd = "shoot";
            ack.ok = false;
            if (!armed_) {
                ack.why = "disarmed";
                break;
            }
            // Tank first: an empty tank always raises Fault::TankEmpty, so
            // checking the fault first would make the "tank" code unreachable.
            if (!tankOk_) {
                ack.why = "tank";
                break;
            }
            if (fault_ != Fault::None) {
                ack.why = "fault";
                break;
            }
            const float p = clampf(c.pan, cfg_.limits.panMin, cfg_.limits.panMax);
            const float t = clampf(c.tilt, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            const char* why = nullptr;
            if (shooter_.request(p, t, c.ms, now, &why)) {
                targetPan_ = p;
                targetTilt_ = t;
                ack.ok = true;
            } else {
                ack.why = why;
            }
            break;
        }

        case CmdType::Charge:
            charge_ = c.flag;
            ack.present = true;
            ack.cmd = "charge";
            ack.ok = true;
            break;

        case CmdType::Fan:
            fanCmd_ = c.flag;
            ack.present = true;
            ack.cmd = "fan";
            ack.ok = true;
            break;

        case CmdType::Cfg:
            ack.present = true;
            ack.cmd = "cfg";
            if (c.panMin >= c.panMax || c.tiltMin >= c.tiltMax ||
                !withinMechanicalEnvelope(c.panMin) || !withinMechanicalEnvelope(c.panMax) ||
                !withinMechanicalEnvelope(c.tiltMin) || !withinMechanicalEnvelope(c.tiltMax)) {
                // Also rejects a NaN limit for free: withinMechanicalEnvelope()
                // is written as an "inside" test, so NaN (which compares false
                // against everything) fails it and is caught here, closing a
                // defence-in-depth gap for a Command built directly in code
                // rather than parsed (parseCommand already screens NaN out).
                ack.ok = false;
                ack.why = "bad";
                break;
            }
            cfg_.limits = Limits{c.panMin, c.panMax, c.tiltMin, c.tiltMax};
            targetPan_ = clampf(targetPan_, c.panMin, c.panMax);
            targetTilt_ = clampf(targetTilt_, c.tiltMin, c.tiltMax);
            // Narrowing limits is a safety action: the operator is saying
            // "never point there." A shot already in flight latched its own
            // target inside Shooter at request() time, so reclamping the
            // controller's target above does not touch it -- without this,
            // a shot could still land (and spray) outside the new cone.
            if (shooter_.state() != ShooterState::Idle &&
                (shooter_.targetPan() < c.panMin || shooter_.targetPan() > c.panMax ||
                 shooter_.targetTilt() < c.tiltMin || shooter_.targetTilt() > c.tiltMax)) {
                shooter_.abort(now);
            }
            ack.ok = true;
            break;

        case CmdType::None:
            break;
    }

    return ack;
}

void Controller::update(Millis now, bool tankSwitchClosed, float tempC) {
    // The first update() call has no prior tick to measure against: charging
    // it with now - lastUpdate_(0) would count however long setup() took
    // (hundreds of ms on real hardware) as slew time and snap the head to
    // whatever target was already commanded. Treat the first call as dt = 0
    // instead, the same way linkUp_ guards the heartbeat check before any
    // command has ever arrived.
    const Millis dt = started_ ? now - lastUpdate_ : 0;
    started_ = true;
    lastUpdate_ = now;
    temp_ = tempC;

    if (!tankSwitchClosed) {
        if (!tankLowPending_) {
            tankLowPending_ = true;
            tankLowSince_ = now;
        } else if (now - tankLowSince_ >= cfg_.tankDebounceMs) {
            tankOk_ = false;
        }
    } else {
        tankLowPending_ = false;
        tankOk_ = true;
    }

    // Fault precedence, highest first: ValveTimeout, Overtemp, TempSensor,
    // TankEmpty.
    //
    // Fault::ValveTimeout outranks everything and is sticky: it does not
    // clear on its own from a healthy tank or temperature reading, only from
    // an explicit disarm (handled in handle()). Skip the ordinary fault
    // computation entirely while it is latched.
    if (valveTimeoutLatched_) {
        fault_ = Fault::ValveTimeout;
    } else {
        const bool tempValid = isValidTempReading(temp_);

        // Overtemp outranks tank level and disarms immediately. A reading
        // that fails isValidTempReading() (NaN, or DallasTemperature's -127
        // "disconnected probe" sentinel) can never satisfy `>= overtempC`
        // here, so it falls through to the TempSensor check below instead of
        // ever being misread as "not hot".
        if (tempValid && temp_ >= cfg_.overtempC) {
            fault_ = Fault::Overtemp;
            armed_ = false;
            shooter_.abort(now);
        } else if (fault_ == Fault::Overtemp && tempValid && temp_ <= cfg_.overtempClearC) {
            fault_ = Fault::None;
        }

        if (fault_ != Fault::Overtemp) {
            if (!tempValid) {
                // A dead or disconnected sensor must not silently disable
                // thermal protection: disarm, same as overtemp itself.
                fault_ = Fault::TempSensor;
                armed_ = false;
            } else if (fault_ == Fault::TempSensor) {
                fault_ = Fault::None;  // a valid reading returned
            }
        }

        if (fault_ != Fault::Overtemp && fault_ != Fault::TempSensor) {
            fault_ = tankOk_ ? Fault::None : Fault::TankEmpty;
        }
    }

    // The spec says "after 3 s", so silence measured as exactly 3000 ms must
    // already count as timed out, not wait for the next tick past it.
    if (linkUp_ && now - lastCmd_ >= cfg_.heartbeatTimeoutMs) {
        enterSafeState(now);
        linkUp_ = false;
    }

    pan_ = slewToward(pan_, targetPan_, cfg_.slewDegPerSec, dt);
    tilt_ = slewToward(tilt_, targetTilt_, cfg_.slewDegPerSec, dt);
    shooter_.update(now, pan_, tilt_);

    if (temp_ >= cfg_.fanOnC) fanAuto_ = true;
    if (temp_ <= cfg_.fanOffC) fanAuto_ = false;
    fan_ = fanCmd_ || fanAuto_;
}

void Controller::forceSafe(Millis now) {
    // Deliberately identical to the heartbeat-loss path, and deliberately
    // does not touch lastCmd_/linkUp_: those belong exclusively to real phone
    // traffic, so this can never masquerade as a heartbeat.
    enterSafeState(now);
}

void Controller::notifyValveForceClosed(Millis now) {
    // abort() while Open counts the shot and starts the cooldown from `now`;
    // in any other phase it is a safe no-op or simply closes an already-shut
    // valve.
    shooter_.abort(now);
    armed_ = false;
    valveTimeoutLatched_ = true;
    fault_ = Fault::ValveTimeout;
}

void Controller::enterSafeState(Millis now) {
    armed_ = false;
    shooter_.abort(now);
    // Park means "the nominal centre", clamped into whatever the configured
    // limits actually are (cfg is not required to leave 0 inside them).
    targetPan_ = clampf(0.0f, cfg_.limits.panMin, cfg_.limits.panMax);
    targetTilt_ = clampf(0.0f, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
    charge_ = true;
    fanCmd_ = false;  // a phone-commanded fan must not latch on forever
}

Status Controller::status() const {
    Status s;
    s.armed = armed_;
    s.pan = pan_;
    s.tilt = tilt_;
    s.tankOk = tankOk_;
    s.pump = pumpOn();
    s.charge = charge_;
    s.fan = fan_;
    s.temp = temp_;
    s.fault = fault_;
    s.shots = shooter_.shots();
    return s;
}

}  // namespace dwarf
