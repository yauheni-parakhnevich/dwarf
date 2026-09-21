#include "controller.h"

namespace dwarf {

namespace {

// True while a shot owns the head: Move (slewing in), Settle (holding still
// before firing) or Open (water actually leaving the nozzle). Re-pointing the
// head during any of these phases is exactly the bug that let a shot land, or
// a valve open, somewhere other than where it was aimed.
bool shooterBusy(ShooterState s) {
    return s == ShooterState::Move || s == ShooterState::Settle || s == ShooterState::Open;
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
            targetPan_ = 0.0f;
            targetTilt_ = 0.0f;
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
            if (c.panMin >= c.panMax || c.tiltMin >= c.tiltMax) {
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

    // Fault::ValveTimeout outranks everything and is sticky: it does not
    // clear on its own from a healthy tank or temperature reading, only from
    // an explicit disarm (handled in handle()). Skip the ordinary fault
    // computation entirely while it is latched.
    if (valveTimeoutLatched_) {
        fault_ = Fault::ValveTimeout;
    } else {
        // Overtemp outranks tank level and disarms immediately.
        if (temp_ >= cfg_.overtempC) {
            fault_ = Fault::Overtemp;
            armed_ = false;
            shooter_.abort(now);
        } else if (fault_ == Fault::Overtemp && temp_ <= cfg_.overtempClearC) {
            fault_ = Fault::None;
        }
        if (fault_ != Fault::Overtemp) {
            fault_ = tankOk_ ? Fault::None : Fault::TankEmpty;
        }
    }

    if (linkUp_ && now - lastCmd_ > cfg_.heartbeatTimeoutMs) {
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
    targetPan_ = 0.0f;
    targetTilt_ = 0.0f;
    charge_ = true;
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
