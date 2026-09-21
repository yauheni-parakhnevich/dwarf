#include <unity.h>

#include "controller.h"

using namespace dwarf;

void setUp() {}
void tearDown() {}

namespace {

// Advances the controller in 10 ms ticks, which is roughly the real loop rate.
void advance(Controller& c, Millis& now, Millis ms, bool tankClosed = true,
             float temp = 22.0f) {
    const Millis end = now + ms;
    while (now < end) {
        now += 10;
        c.update(now, tankClosed, temp);
    }
}

Command cmd(const char* json) { return parseCommand(json); }

}  // namespace

void test_arm_and_disarm() {
    Controller c;
    Millis now = 0;

    Ack a = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_TRUE(a.present);
    TEST_ASSERT_TRUE(a.ok);
    TEST_ASSERT_EQUAL_STRING("arm", a.cmd);
    TEST_ASSERT_TRUE(c.armed());

    c.handle(cmd("{\"c\":\"arm\",\"v\":false}"), now);
    TEST_ASSERT_FALSE(c.armed());
}

void test_heartbeat_has_no_ack() {
    Controller c;
    Millis now = 0;
    Ack a = c.handle(cmd("{\"c\":\"hb\"}"), now);
    TEST_ASSERT_FALSE(a.present);
}

void test_unknown_command_is_acked_as_bad() {
    Controller c;
    Millis now = 0;
    Ack a = c.handle(cmd("{\"c\":\"launch\"}"), now);
    TEST_ASSERT_TRUE(a.present);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("bad", a.why);
}

void test_aim_is_clamped_to_limits_and_slews() {
    Controller c;  // default limits: pan -60..60, tilt -30..40
    Millis now = 0;
    c.update(now, true, 22.0f);  // prime the first-ever tick, as main.cpp's
                                  // setup() does, so it is not the 100 ms
                                  // window being measured below.

    c.handle(cmd("{\"c\":\"aim\",\"pan\":90.0,\"tilt\":80.0}"), now);
    advance(c, now, 100);  // 120 deg/s for 100 ms is 12 degrees
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 12.0f, c.pan());

    advance(c, now, 2000);  // plenty of time to arrive
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 60.0f, c.pan());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 40.0f, c.tilt());
}

void test_park_returns_to_zero() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"aim\",\"pan\":30.0,\"tilt\":20.0}"), now);
    advance(c, now, 2000);

    Ack a = c.handle(cmd("{\"c\":\"park\"}"), now);
    TEST_ASSERT_TRUE(a.ok);
    advance(c, now, 2000);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.pan());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.tilt());
}

void test_cfg_narrows_limits_and_pulls_target_in() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"aim\",\"pan\":55.0,\"tilt\":0.0}"), now);
    advance(c, now, 2000);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 55.0f, c.pan());

    Ack a = c.handle(
        cmd("{\"c\":\"cfg\",\"panMin\":-30,\"panMax\":30,\"tiltMin\":-20,\"tiltMax\":20}"),
        now);
    TEST_ASSERT_TRUE(a.ok);
    advance(c, now, 2000);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 30.0f, c.pan());
}

void test_cfg_with_inverted_range_is_rejected() {
    Controller c;
    Millis now = 0;
    Ack a = c.handle(
        cmd("{\"c\":\"cfg\",\"panMin\":30,\"panMax\":-30,\"tiltMin\":-20,\"tiltMax\":20}"),
        now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("bad", a.why);

    c.handle(cmd("{\"c\":\"aim\",\"pan\":55.0,\"tilt\":0.0}"), now);
    advance(c, now, 2000);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 55.0f, c.pan());  // old limits still apply
}

void test_first_update_after_boot_does_not_charge_setup_time_to_slew() {
    Controller c;
    // Simulate setup() taking 500ms before loop() ever calls update(), with a
    // command already applied during that window. Stay well under the 3 s
    // heartbeat timeout so the safe-state path does not also reset the target.
    c.handle(cmd("{\"c\":\"aim\",\"pan\":90.0,\"tilt\":0.0}"), 500);  // clamps to 60

    c.update(510, true, 22.0f);  // first update() ever, called after setup()
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.pan());  // must not have snapped

    c.update(520, true, 22.0f);  // a real 10 ms tick
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 1.2f, c.pan());   // 120 deg/s * 10 ms
}

void test_first_update_at_small_now_behaves_as_before() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"aim\",\"pan\":90.0,\"tilt\":80.0}"), now);
    advance(c, now, 2000);  // plenty of time to arrive, exactly as before
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 60.0f, c.pan());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 40.0f, c.tilt());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_arm_and_disarm);
    RUN_TEST(test_heartbeat_has_no_ack);
    RUN_TEST(test_unknown_command_is_acked_as_bad);
    RUN_TEST(test_aim_is_clamped_to_limits_and_slews);
    RUN_TEST(test_park_returns_to_zero);
    RUN_TEST(test_cfg_narrows_limits_and_pulls_target_in);
    RUN_TEST(test_cfg_with_inverted_range_is_rejected);
    RUN_TEST(test_first_update_after_boot_does_not_charge_setup_time_to_slew);
    RUN_TEST(test_first_update_at_small_now_behaves_as_before);
    return UNITY_END();
}
