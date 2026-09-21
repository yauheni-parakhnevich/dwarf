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

void test_cfg_narrowing_limits_aborts_an_in_flight_shot_outside_the_new_cone() {
    Controller c;  // default limits: pan -60..60, tilt -30..40
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    Ack shot = c.handle(cmd("{\"c\":\"shoot\",\"pan\":55.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(shot.ok);

    advance(c, now, 100);  // still moving toward 55 degrees (needs ~460 ms)
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);
    TEST_ASSERT_FALSE(c.valveOpen());

    // Narrow the cone so the in-flight target (pan 55) falls outside it.
    Ack a = c.handle(
        cmd("{\"c\":\"cfg\",\"panMin\":-30,\"panMax\":30,\"tiltMin\":-20,\"tiltMax\":20}"),
        now);
    TEST_ASSERT_TRUE(a.ok);
    TEST_ASSERT_FALSE(c.valveOpen());
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Idle);  // in-flight shot aborted
}

void test_cfg_narrowing_limits_leaves_an_in_flight_shot_inside_the_new_cone_alone() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    Ack shot = c.handle(cmd("{\"c\":\"shoot\",\"pan\":20.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(shot.ok);

    advance(c, now, 100);  // still moving toward 20 degrees
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);

    // The in-flight target (pan 20) is still inside the narrowed cone.
    Ack a = c.handle(
        cmd("{\"c\":\"cfg\",\"panMin\":-30,\"panMax\":30,\"tiltMin\":-20,\"tiltMax\":20}"),
        now);
    TEST_ASSERT_TRUE(a.ok);
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);  // not aborted

    advance(c, now, 600);  // plenty of time to settle, open and finish the burst
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);
}

void test_aim_mid_move_does_not_repoint_the_shot() {
    Controller c;  // default limits, default slew 120 deg/s
    Millis now = 0;
    c.update(now, true, 22.0f);  // prime the first tick
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    Ack shot = c.handle(cmd("{\"c\":\"shoot\",\"pan\":20.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(shot.ok);

    advance(c, now, 50);  // partway there, still Move
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);
    TEST_ASSERT_TRUE(c.pan() > 0.0f && c.pan() < 20.0f);

    // A cat moved: the phone tries to redirect the head mid-flight. This must
    // be silently ignored -- the shot in flight owns the head until it lands.
    c.handle(cmd("{\"c\":\"aim\",\"pan\":60.0,\"tilt\":40.0}"), now);

    bool sawOpen = false;
    for (int i = 0; i < 300 && !sawOpen; ++i) {
        now += 10;
        c.update(now, true, 22.0f);
        if (c.valveOpen()) {
            sawOpen = true;
            // The valve must never open anywhere but the originally requested angle.
            TEST_ASSERT_FLOAT_WITHIN(0.6f, 20.0f, c.pan());
            TEST_ASSERT_FLOAT_WITHIN(0.6f, 0.0f, c.tilt());
        }
    }
    TEST_ASSERT_TRUE(sawOpen);

    advance(c, now, 1000);  // let the burst and cooldown machinery settle
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);
    // The dropped aim was never queued: the head never heads toward (60,40).
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 20.0f, c.pan());
}

void test_aim_mid_settle_does_not_repoint_the_shot() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);

    Ack shot = c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);
    TEST_ASSERT_TRUE(shot.ok);

    now += 10;
    c.update(now, true, 22.0f);  // already at (0,0): arrives immediately -> Settle
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Settle);

    c.handle(cmd("{\"c\":\"aim\",\"pan\":60.0,\"tilt\":40.0}"), now);

    bool sawOpen = false;
    for (int i = 0; i < 50 && !sawOpen; ++i) {
        now += 10;
        c.update(now, true, 22.0f);
        if (c.valveOpen()) {
            sawOpen = true;
            TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, c.pan());
            TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, c.tilt());
        }
    }
    TEST_ASSERT_TRUE(sawOpen);
}

void test_aim_mid_open_does_not_repoint_the_head() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);

    advance(c, now, 200);  // settle finished, valve open
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Open);
    TEST_ASSERT_TRUE(c.valveOpen());

    c.handle(cmd("{\"c\":\"aim\",\"pan\":60.0,\"tilt\":40.0}"), now);
    advance(c, now, 50);  // still mid-burst
    TEST_ASSERT_TRUE(c.valveOpen());
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, c.pan());  // never budged toward the aim

    advance(c, now, 400);  // burst finishes
    TEST_ASSERT_FALSE(c.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 0.0f, c.pan());  // aim was dropped entirely
}

void test_park_is_refused_busy_during_move() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":20.0,\"tilt\":0.0,\"ms\":300}"), now);

    advance(c, now, 50);
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);

    Ack a = c.handle(cmd("{\"c\":\"park\"}"), now);
    TEST_ASSERT_TRUE(a.present);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("busy", a.why);
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Move);  // untouched

    advance(c, now, 1000);  // the shot still lands where it was aimed
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);
}

void test_park_is_refused_busy_during_settle() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);

    now += 10;
    c.update(now, true, 22.0f);
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Settle);

    Ack a = c.handle(cmd("{\"c\":\"park\"}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("busy", a.why);
}

void test_park_is_refused_busy_during_open() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);

    advance(c, now, 200);  // settle finished, valve open
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Open);

    Ack a = c.handle(cmd("{\"c\":\"park\"}"), now);
    TEST_ASSERT_FALSE(a.ok);
    TEST_ASSERT_EQUAL_STRING("busy", a.why);
    TEST_ASSERT_TRUE(c.valveOpen());  // untouched by the refused park
}

void test_aim_and_park_allowed_during_cooldown() {
    Controller c;
    Millis now = 0;
    c.update(now, true, 22.0f);
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);

    advance(c, now, 500);  // settle + burst complete -> Cooldown
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Cooldown);

    c.handle(cmd("{\"c\":\"aim\",\"pan\":30.0,\"tilt\":10.0}"), now);
    advance(c, now, 500);
    TEST_ASSERT_TRUE(c.pan() > 0.0f);  // aim took effect: the head is moving

    Ack a = c.handle(cmd("{\"c\":\"park\"}"), now);
    TEST_ASSERT_TRUE(a.ok);
    advance(c, now, 2000);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.pan());
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.tilt());
}

void test_status_reflects_every_field_of_a_live_controller() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"charge\",\"v\":false}"), now);
    c.handle(cmd("{\"c\":\"fan\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"aim\",\"pan\":25.0,\"tilt\":-10.0}"), now);
    advance(c, now, 500, /*tankClosed=*/true, /*temp=*/33.5f);  // head arrives

    c.handle(cmd("{\"c\":\"shoot\",\"pan\":25.0,\"tilt\":-10.0,\"ms\":300}"), now);
    advance(c, now, 500, true, 33.5f);  // settle and burst complete

    Status s = c.status();
    TEST_ASSERT_TRUE(s.armed);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 25.0f, s.pan);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, -10.0f, s.tilt);
    TEST_ASSERT_TRUE(s.tankOk);
    TEST_ASSERT_TRUE(s.pump);      // armed && tankOk && no fault
    TEST_ASSERT_FALSE(s.charge);   // explicitly turned off
    TEST_ASSERT_TRUE(s.fan);       // commanded on
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 33.5f, s.temp);
    TEST_ASSERT_TRUE(s.fault == Fault::None);
    TEST_ASSERT_EQUAL_UINT32(1, s.shots);
}

void test_forceSafe_reaches_full_safe_state_without_using_handle() {
    Controller c;
    Millis now = 0;

    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"charge\",\"v\":false}"), now);
    c.handle(cmd("{\"c\":\"aim\",\"pan\":40.0,\"tilt\":0.0}"), now);
    advance(c, now, 2000);  // head arrives at 40 degrees
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 40.0f, c.pan());
    TEST_ASSERT_TRUE(c.armed());
    TEST_ASSERT_FALSE(c.chargeOn());

    // Simulate the Arduino recovery path noticing the link is bad and calling
    // the local safe-state API repeatedly, with no real phone traffic at all
    // for 10 seconds -- exactly the measured scenario from the bug report,
    // but via forceSafe() instead of a synthesised {"c":"arm","v":false}
    // pushed through handle(). A synthesised handle() call would have kept
    // the link "looking alive" and left the charger off and the head aimed
    // at 40 degrees forever.
    for (int i = 0; i < 5; ++i) {
        advance(c, now, 2000);
        c.forceSafe(now);
    }

    TEST_ASSERT_FALSE(c.armed());
    TEST_ASSERT_TRUE(c.chargeOn());  // charger actually recovered
    advance(c, now, 2000);           // let the head slew back
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, c.pan());  // actually parked

    // forceSafe must not have refreshed the heartbeat bookkeeping either: a
    // real re-arm afterwards still runs its own, ordinary 3 s heartbeat
    // clock from the moment it happens, unaffected by any of the forceSafe
    // calls in its past.
    Ack rearm = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_TRUE(rearm.ok);
    TEST_ASSERT_TRUE(c.armed());
    advance(c, now, 2999);
    TEST_ASSERT_TRUE(c.armed());
    advance(c, now, 2);
    TEST_ASSERT_FALSE(c.armed());
}

void test_notifyValveForceClosed_counts_shot_and_latches_fault() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);
    advance(c, now, 200);  // settle done, valve open
    TEST_ASSERT_TRUE(c.valveOpen());

    c.notifyValveForceClosed(now);
    TEST_ASSERT_FALSE(c.valveOpen());
    TEST_ASSERT_FALSE(c.armed());
    TEST_ASSERT_TRUE(c.fault() == Fault::ValveTimeout);
    TEST_ASSERT_EQUAL_UINT32(1, c.status().shots);                  // burst counted
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Cooldown);   // cooldown from now
}

void test_valve_timeout_fault_rejects_arm_until_explicit_disarm_then_recovers() {
    Controller c;
    Millis now = 0;
    c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    c.handle(cmd("{\"c\":\"shoot\",\"pan\":0.0,\"tilt\":0.0,\"ms\":300}"), now);
    advance(c, now, 200);
    c.notifyValveForceClosed(now);

    Ack rearm = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_FALSE(rearm.ok);
    TEST_ASSERT_EQUAL_STRING("fault", rearm.why);

    // Sticky: time alone must not clear it.
    advance(c, now, 10000);
    TEST_ASSERT_TRUE(c.fault() == Fault::ValveTimeout);

    // The operator's explicit disarm is what acknowledges the fault.
    Ack disarm = c.handle(cmd("{\"c\":\"arm\",\"v\":false}"), now);
    TEST_ASSERT_TRUE(disarm.ok);
    TEST_ASSERT_TRUE(c.fault() == Fault::None);

    // Recovery: disarm, then re-arm.
    Ack rearm2 = c.handle(cmd("{\"c\":\"arm\",\"v\":true}"), now);
    TEST_ASSERT_TRUE(rearm2.ok);
    TEST_ASSERT_TRUE(c.armed());
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
    RUN_TEST(test_cfg_narrowing_limits_aborts_an_in_flight_shot_outside_the_new_cone);
    RUN_TEST(test_cfg_narrowing_limits_leaves_an_in_flight_shot_inside_the_new_cone_alone);
    RUN_TEST(test_status_reflects_every_field_of_a_live_controller);
    RUN_TEST(test_aim_mid_move_does_not_repoint_the_shot);
    RUN_TEST(test_aim_mid_settle_does_not_repoint_the_shot);
    RUN_TEST(test_aim_mid_open_does_not_repoint_the_head);
    RUN_TEST(test_park_is_refused_busy_during_move);
    RUN_TEST(test_park_is_refused_busy_during_settle);
    RUN_TEST(test_park_is_refused_busy_during_open);
    RUN_TEST(test_aim_and_park_allowed_during_cooldown);
    RUN_TEST(test_forceSafe_reaches_full_safe_state_without_using_handle);
    RUN_TEST(test_notifyValveForceClosed_counts_shot_and_latches_fault);
    RUN_TEST(test_valve_timeout_fault_rejects_arm_until_explicit_disarm_then_recovers);
    return UNITY_END();
}
