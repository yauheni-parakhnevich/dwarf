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

void test_pump_runs_only_while_armed_and_healthy() {
    Controller c;
    Millis now = 0;
    advance(c, now, 100);
    TEST_ASSERT_FALSE(c.pumpOn());

    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    advance(c, now, 100);
    TEST_ASSERT_TRUE(c.pumpOn());

    c.handle(cmd("{\"c\":\"arm\",\"v\":false}"), now);
    advance(c, now, 100);
    TEST_ASSERT_FALSE(c.pumpOn());
}

void test_tank_low_is_debounced_then_faults_and_blocks_shots() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    advance(c, now, 1000, /*tankClosed=*/false);  // 1 s of low, under the 2 s debounce
    TEST_ASSERT_TRUE(c.fault() == Fault::None);
    TEST_ASSERT_TRUE(c.pumpOn());

    advance(c, now, 1500, /*tankClosed=*/false);  // now past 2 s
    TEST_ASSERT_TRUE(c.fault() == Fault::TankEmpty);
    TEST_ASSERT_FALSE(c.pumpOn());

    Ack a = c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("tank", a.why);

    advance(c, now, 100, /*tankClosed=*/true);  // refilled
    TEST_ASSERT_TRUE(c.fault() == Fault::None);
    TEST_ASSERT_TRUE(c.pumpOn());
}

void test_overtemp_disarms_and_clears_with_hysteresis() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    advance(c, now, 100, true, 22.0f);
    TEST_ASSERT_TRUE(c.armed());

    advance(c, now, 100, true, 61.0f);
    TEST_ASSERT_TRUE(c.fault() == Fault::Overtemp);
    TEST_ASSERT_FALSE(c.armed());

    Ack a = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("fault", a.why);

    advance(c, now, 100, true, 57.0f);  // still above the clear threshold
    TEST_ASSERT_TRUE(c.fault() == Fault::Overtemp);

    advance(c, now, 100, true, 54.0f);
    TEST_ASSERT_TRUE(c.fault() == Fault::None);

    a = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_TRUE(a.ok);
}

void test_fan_runs_on_command_or_heat() {
    Controller c;
    Millis now = 0;

    advance(c, now, 100, true, 22.0f);
    TEST_ASSERT_FALSE(c.fanOn());

    c.handle(cmd("{\"c\":\"fan\",\"v\":true}"), now);
    advance(c, now, 100, true, 22.0f);
    TEST_ASSERT_TRUE(c.fanOn());

    c.handle(cmd("{\"c\":\"fan\",\"v\":false}"), now);
    advance(c, now, 100, true, 41.0f);  // hot: auto mode takes over
    TEST_ASSERT_TRUE(c.fanOn());

    advance(c, now, 100, true, 37.0f);  // between the thresholds: stays on
    TEST_ASSERT_TRUE(c.fanOn());

    advance(c, now, 100, true, 34.0f);  // below the off threshold
    TEST_ASSERT_FALSE(c.fanOn());
}

void test_shoot_is_rejected_when_disarmed() {
    Controller c;
    Millis now = 0;
    Ack a = c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("disarmed", a.why);
    TEST_ASSERT_FALSE(c.valveOpen());
}

void test_arm_aim_shoot_cooldown_sequence() {
    Controller c;
    Millis now = 0;
    char buf[256];

    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"aim\",\"pan\":12.5,\"tilt\":-3.0}"), now);
    advance(c, now, 500);  // head arrives
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 12.5f, c.pan());

    Ack a = c.handle(cmd("{\"c\":\"shoot\",\"pan\":14.0,\"tilt\":-2.5,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(a.ok);
    TEST_ASSERT_EQUAL_STRING("shoot", a.cmd);

    advance(c, now, 100);  // moving 1.5 degrees, then settling
    TEST_ASSERT_FALSE(c.valveOpen());

    advance(c, now, 200);  // settle finished, valve opens
    TEST_ASSERT_TRUE(c.valveOpen());

    advance(c, now, 400);  // burst over
    TEST_ASSERT_FALSE(c.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);

    a = c.handle(cmd("{\"c\":\"shoot\",\"pan\":14.0,\"tilt\":-2.5,\"ms\":300}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("cooldown", a.why);

    // The rejection serialises exactly as the shared fixture says it should.
    formatAck(a.cmd, a.ok, a.why, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}", buf);

    // Wait out the 5 s cooldown while keeping the link alive, exactly as the
    // phone does. Without the heartbeats the 3 s timeout would disarm first.
    for (int i = 0; i < 6; ++i) {
        advance(c, now, 1000);
        c.handle(cmd("{\"c\":\"hb\"}"), now);
    }

    a = c.handle(cmd("{\"c\":\"shoot\",\"pan\":14.0,\"tilt\":-2.5,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(a.ok);
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
    RUN_TEST(test_pump_runs_only_while_armed_and_healthy);
    RUN_TEST(test_tank_low_is_debounced_then_faults_and_blocks_shots);
    RUN_TEST(test_overtemp_disarms_and_clears_with_hysteresis);
    RUN_TEST(test_fan_runs_on_command_or_heat);
    RUN_TEST(test_shoot_is_rejected_when_disarmed);
    RUN_TEST(test_arm_aim_shoot_cooldown_sequence);
    return UNITY_END();
}
