#include "servo.h"

#include <cmath>

namespace dwarf {

float clampf(float v, float lo, float hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

uint16_t angleToMicros(float angleDeg, float trimUs) {
    if (!std::isfinite(angleDeg)) angleDeg = 0.0f;
    if (!std::isfinite(trimUs)) trimUs = 0.0f;
    const float us = 1500.0f + angleDeg * (1000.0f / 90.0f) + trimUs;
    return static_cast<uint16_t>(std::lround(clampf(us, 500.0f, 2500.0f)));
}

float slewToward(float current, float target, float degPerSec, uint32_t dtMs) {
    const bool currentFinite = std::isfinite(current);
    const bool targetFinite = std::isfinite(target);
    if (!currentFinite && !targetFinite) return 0.0f;
    if (!targetFinite) return current;
    if (!currentFinite) return target;

    const float rate = std::fabs(degPerSec);
    const float step = rate * (static_cast<float>(dtMs) / 1000.0f);
    const float delta = target - current;
    if (std::fabs(delta) <= step) return target;
    return current + (delta > 0.0f ? step : -step);
}

}  // namespace dwarf
