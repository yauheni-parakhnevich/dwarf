#include "controller.h"

namespace dwarf {

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
            armed_ = c.flag;
            if (!armed_) shooter_.abort(now);
            ack.ok = true;
            break;

        case CmdType::Aim:
            targetPan_ = clampf(c.pan, cfg_.limits.panMin, cfg_.limits.panMax);
            targetTilt_ = clampf(c.tilt, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            break;

        case CmdType::Park:
            targetPan_ = 0.0f;
            targetTilt_ = 0.0f;
            ack.present = true;
            ack.cmd = "park";
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
            ack.ok = true;
            break;

        case CmdType::None:
            break;
    }

    return ack;
}

void Controller::update(Millis now, bool tankSwitchClosed, float tempC) {
    const Millis dt = now - lastUpdate_;
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
