#include <unity.h>

#include "servo.h"

using namespace dwarf;

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

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_clamp);
    RUN_TEST(test_angle_to_micros_centre_and_ends);
    RUN_TEST(test_angle_to_micros_applies_trim_and_saturates);
    RUN_TEST(test_slew_limits_movement_per_tick);
    RUN_TEST(test_slew_snaps_when_target_is_close);
    RUN_TEST(test_slew_with_zero_dt_does_not_move);
    return UNITY_END();
}
