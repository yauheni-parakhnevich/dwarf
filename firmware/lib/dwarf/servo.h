#pragma once
#include <cstdint>

namespace dwarf {

// Constrains v to [lo, hi].
float clampf(float v, float lo, float hi);

// Maps -90..+90 degrees to a 500..2500 us servo pulse, plus a per-servo trim in
// microseconds, saturating at the pulse limits. A non-finite angleDeg or trimUs
// (NaN or infinity) is treated as zero rather than propagated: a centred pulse
// is a safe default, whereas a NaN pulse width is not.
uint16_t angleToMicros(float angleDeg, float trimUs = 0.0f);

// Moves current toward target by at most degPerSec * dtMs (using the magnitude
// of degPerSec, so a sign error in configuration cannot drive the head away
// from the target), so the head turns smoothly instead of snapping and shaking
// the gnome.
//
// Non-finite inputs are handled explicitly rather than propagated: a
// non-finite target is ignored and current is returned unchanged; a
// non-finite current with a finite target heals immediately to target; and
// if both are non-finite the result is 0, the park angle, since the head's
// position is unknown.
float slewToward(float current, float target, float degPerSec, uint32_t dtMs);

}  // namespace dwarf
