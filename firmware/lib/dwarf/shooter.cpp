#include "shooter.h"

#include <cmath>

namespace dwarf {

bool Shooter::request(float pan, float tilt, uint16_t ms, Millis now, const char** why) {
    if (state_ != ShooterState::Idle) {
        if (why != nullptr) {
            *why = (state_ == ShooterState::Cooldown) ? "cooldown" : "busy";
        }
        return false;
    }
    if (ms == 0) {
        if (why != nullptr) *why = "bad";
        return false;
    }

    targetPan_ = pan;
    targetTilt_ = tilt;
    burstMs_ = (ms > cfg_.maxBurstMs) ? cfg_.maxBurstMs : ms;
    state_ = ShooterState::Move;
    stamp_ = now;
    return true;
}

void Shooter::update(Millis now, float currentPan, float currentTilt) {
    switch (state_) {
        case ShooterState::Move: {
            const bool arrived =
                std::fabs(currentPan - targetPan_) <= cfg_.settleToleranceDeg &&
                std::fabs(currentTilt - targetTilt_) <= cfg_.settleToleranceDeg;
            if (arrived) {
                state_ = ShooterState::Settle;
                stamp_ = now;
            }
            break;
        }
        case ShooterState::Settle:
            if (now - stamp_ >= cfg_.settleMs) {
                state_ = ShooterState::Open;
                stamp_ = now;
                valve_ = true;
            }
            break;
        case ShooterState::Open:
            if (now - stamp_ >= burstMs_) {
                valve_ = false;
                ++shots_;
                state_ = ShooterState::Cooldown;
                stamp_ = now;
            }
            break;
        case ShooterState::Cooldown:
            if (now - stamp_ >= cfg_.cooldownMs) state_ = ShooterState::Idle;
            break;
        case ShooterState::Idle:
            break;
    }
}

void Shooter::abort() {
    valve_ = false;
    state_ = ShooterState::Idle;
}

}  // namespace dwarf
