#pragma once
#include "types.h"

namespace dwarf {

enum class ShooterState { Idle, Move, Settle, Open, Cooldown };

struct ShooterConfig {
    uint16_t settleMs = 150;         // let the servos stop swinging before firing
    uint16_t maxBurstMs = 500;       // hard cap, independent of what the phone asks
    uint32_t cooldownMs = 5000;      // hard minimum gap between shots
    float settleToleranceDeg = 0.5f; // "arrived" window for both axes
};

class Shooter {
  public:
    explicit Shooter(ShooterConfig cfg = ShooterConfig{}) : cfg_(cfg) {}

    // Starts a shot. Returns false and sets *why to "busy", "cooldown" or "bad"
    // when the request cannot be accepted. The caller checks arm state, tank and
    // faults before calling.
    bool request(float pan, float tilt, uint16_t ms, Millis now, const char** why);

    // Advances the state machine. currentPan/currentTilt are the live servo angles.
    void update(Millis now, float currentPan, float currentTilt);

    // Closes the valve and returns to Idle. Used by safety paths.
    void abort();

    ShooterState state() const { return state_; }
    bool valveOpen() const { return valve_; }
    uint32_t shots() const { return shots_; }
    float targetPan() const { return targetPan_; }
    float targetTilt() const { return targetTilt_; }

  private:
    ShooterConfig cfg_;
    ShooterState state_ = ShooterState::Idle;
    bool valve_ = false;
    uint32_t shots_ = 0;
    float targetPan_ = 0.0f;
    float targetTilt_ = 0.0f;
    uint16_t burstMs_ = 0;
    Millis stamp_ = 0;
};

}  // namespace dwarf
