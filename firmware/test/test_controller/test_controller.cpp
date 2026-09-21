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

void test_link_loss_disarms_parks_and_restores_charging() {
    Controller c;
    Millis now = 0;

    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"charge\",\"v\":false}"), now);
    c.handle(cmd("{\"c\":\"aim\",\"pan\":40.0,\"tilt\":10.0}"), now);
    advance(c, now, 1000);
    TEST_ASSERT_TRUE(c.armed());
    TEST_ASSERT_FALSE(c.chargeOn());

    advance(c, now, 2500);  // 3.5 s total with no command
    TEST_ASSERT_FALSE(c.armed());
    TEST_ASSERT_TRUE(c.chargeOn());
    TEST_ASSERT_FALSE(c.pumpOn());

    advance(c, now, 2000);  // head slews back to park
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.pan());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.tilt());
}

void test_heartbeats_keep_the_link_alive() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    for (int i = 0; i < 10; ++i) {
        advance(c, now, 1000);
        c.handle(cmd("{\"c\":\"hb\"}"), now);
    }

    TEST_ASSERT_TRUE(c.armed());
}

void test_link_loss_disarms_but_does_not_shorten_cooldown() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":400}"), now);
    advance(c, now, 200);  // settle done, valve open
    TEST_ASSERT_TRUE(c.valveOpen());

    advance(c, now, 600);  // burst finished on its own, now cooling down
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Cooldown);

    advance(c, now, 2600);  // 3.4 s since the last command: link is dead
    TEST_ASSERT_FALSE(c.valveOpen());
    TEST_ASSERT_FALSE(c.armed());
    // abort() ran, but Shooter::abort() deliberately leaves an in-progress
    // Cooldown alone (it only closes the valve) rather than forcing Idle: a
    // flapping link must not be usable to fire two shots inside the 5 s
    // backstop between shots. The cooldown that started when the burst ended
    // (at t=560ms, so it is due to expire at t=5560ms) is still running.
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Cooldown);

    // The phone reconnects and re-arms; a shot attempted before the original
    // cooldown window ends must still be rejected.
    Ack rearm = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_TRUE(rearm.ok);

    Ack retry = c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":400}"), now);
    TEST_ASSERT_FALSE(retry.ok);
    TEST_ASSERT_EQUAL_STRING("cooldown", retry.why);

    // Wait out the remainder of the *original* cooldown window while keeping
    // the link alive with heartbeats, exactly as Task 9's test does.
    for (int i = 0; i < 3; ++i) {
        advance(c, now, 1000);
        c.handle(cmd("{\"c\":\"hb\"}"), now);
    }

    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Idle);
    Ack again = c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":400}"), now);
    TEST_ASSERT_TRUE(again.ok);
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
    RUN_TEST(test_link_loss_disarms_parks_and_restores_charging);
    RUN_TEST(test_heartbeats_keep_the_link_alive);
    RUN_TEST(test_link_loss_disarms_but_does_not_shorten_cooldown);
    return UNITY_END();
}
