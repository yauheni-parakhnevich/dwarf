#pragma once
#include <cstdint>

namespace dwarf {

// Constrains v to [lo, hi].
float clampf(float v, float lo, float hi);

// Maps -90..+90 degrees to a 500..2500 us servo pulse, plus a per-servo trim in
// microseconds, saturating at the pulse limits.
uint16_t angleToMicros(float angleDeg, float trimUs = 0.0f);

// Moves current toward target by at most degPerSec * dtMs, so the head turns
// smoothly instead of snapping and shaking the gnome.
float slewToward(float current, float target, float degPerSec, uint32_t dtMs);

}  // namespace dwarf
