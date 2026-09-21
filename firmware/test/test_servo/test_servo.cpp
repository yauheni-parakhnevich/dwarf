#include <unity.h>

#include <cmath>
#include <limits>

#include "servo.h"

using namespace dwarf;

namespace {
float nan() { return std::numeric_limits<float>::quiet_NaN(); }
float inf() { return std::numeric_limits<float>::infinity(); }
}  // namespace

void setUp() {}
void tearDown() {}

void test_clamp() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 5.0f, clampf(5.0f, -60.0f, 60.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -60.0f, clampf(-90.0f, -60.0f, 60.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 60.0f, clampf(90.0f, -60.0f, 60.0f));
}

void test_angle_to_micros_centre_and_ends() {
    TEST_ASSERT_EQUAL_UINT16(1500, angleToMicros(0.0f));
    TEST_ASSERT_EQUAL_UINT16(2500, angleToMicros(90.0f));
    TEST_ASSERT_EQUAL_UINT16(500, angleToMicros(-90.0f));
}

void test_angle_to_micros_applies_trim_and_saturates() {
    TEST_ASSERT_EQUAL_UINT16(1550, angleToMicros(0.0f, 50.0f));
    TEST_ASSERT_EQUAL_UINT16(2500, angleToMicros(90.0f, 200.0f));
    TEST_ASSERT_EQUAL_UINT16(500, angleToMicros(-90.0f, -200.0f));
}

void test_slew_limits_movement_per_tick() {
    // 120 deg/s over 100 ms is 12 degrees.
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 12.0f, slewToward(0.0f, 45.0f, 120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -12.0f, slewToward(0.0f, -45.0f, 120.0f, 100));
}

void test_slew_snaps_when_target_is_close() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 3.0f, slewToward(0.0f, 3.0f, 120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 7.0f, slewToward(7.0f, 7.0f, 120.0f, 100));
}

void test_slew_with_zero_dt_does_not_move() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, slewToward(0.0f, 45.0f, 120.0f, 0));
}

void test_angle_to_micros_nonfinite_angle_is_treated_as_zero() {
    // NaN/infinite angle centres the head instead of producing a garbage
    // pulse width or saturating as if it were a huge finite angle.
    TEST_ASSERT_EQUAL_UINT16(1500, angleToMicros(nan()));
    TEST_ASSERT_EQUAL_UINT16(1500, angleToMicros(-inf()));
    // A NaN angle with a real trim still applies the trim.
    TEST_ASSERT_EQUAL_UINT16(1550, angleToMicros(nan(), 50.0f));
}

void test_angle_to_micros_nonfinite_trim_is_treated_as_zero() {
    TEST_ASSERT_EQUAL_UINT16(1500, angleToMicros(0.0f, nan()));
    TEST_ASSERT_EQUAL_UINT16(2500, angleToMicros(90.0f, inf()));
}

void test_slew_uses_rate_magnitude_regardless_of_sign() {
    // A negative degPerSec must still move toward the target, not away from it.
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 12.0f, slewToward(0.0f, 45.0f, -120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -12.0f, slewToward(0.0f, -45.0f, -120.0f, 100));
}

void test_slew_ignores_nonfinite_target() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 5.0f, slewToward(5.0f, nan(), 120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 5.0f, slewToward(5.0f, inf(), 120.0f, 100));
}

void test_slew_heals_nonfinite_current_toward_finite_target() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.0f, slewToward(nan(), 45.0f, 120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.0f, slewToward(inf(), 45.0f, 120.0f, 100));
}

void test_slew_both_nonfinite_returns_park_angle() {
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, slewToward(nan(), nan(), 120.0f, 100));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, slewToward(inf(), nan(), 120.0f, 100));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_clamp);
    RUN_TEST(test_angle_to_micros_centre_and_ends);
    RUN_TEST(test_angle_to_micros_applies_trim_and_saturates);
    RUN_TEST(test_slew_limits_movement_per_tick);
    RUN_TEST(test_slew_snaps_when_target_is_close);
    RUN_TEST(test_slew_with_zero_dt_does_not_move);
    RUN_TEST(test_angle_to_micros_nonfinite_angle_is_treated_as_zero);
    RUN_TEST(test_angle_to_micros_nonfinite_trim_is_treated_as_zero);
    RUN_TEST(test_slew_uses_rate_magnitude_regardless_of_sign);
    RUN_TEST(test_slew_ignores_nonfinite_target);
    RUN_TEST(test_slew_heals_nonfinite_current_toward_finite_target);
    RUN_TEST(test_slew_both_nonfinite_returns_park_angle);
    return UNITY_END();
}
