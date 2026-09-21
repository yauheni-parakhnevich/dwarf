#include <unity.h>

#include <limits>

#include "shooter.h"

using namespace dwarf;

void setUp() {}
void tearDown() {}

void test_full_shot_sequence() {
    Shooter s;  // defaults: settle 150 ms, max burst 500 ms, cooldown 5000 ms
    const char* why = nullptr;

    TEST_ASSERT_TRUE(s.request(10.0f, -5.0f, 300, 1000, &why));
    TEST_ASSERT_TRUE(s.state() == ShooterState::Move);

    s.update(1010, 0.0f, 0.0f);  // servos have not arrived yet
    TEST_ASSERT_TRUE(s.state() == ShooterState::Move);
    TEST_ASSERT_FALSE(s.valveOpen());

    s.update(1100, 10.0f, -5.0f);  // arrived
    TEST_ASSERT_TRUE(s.state() == ShooterState::Settle);
    TEST_ASSERT_FALSE(s.valveOpen());

    s.update(1240, 10.0f, -5.0f);  // 140 ms of settling, not enough
    TEST_ASSERT_TRUE(s.state() == ShooterState::Settle);

    s.update(1250, 10.0f, -5.0f);  // 150 ms, valve opens
    TEST_ASSERT_TRUE(s.state() == ShooterState::Open);
    TEST_ASSERT_TRUE(s.valveOpen());

    s.update(1500, 10.0f, -5.0f);  // 250 ms into a 300 ms burst
    TEST_ASSERT_TRUE(s.valveOpen());

    s.update(1550, 10.0f, -5.0f);  // burst complete
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
    TEST_ASSERT_EQUAL_UINT32(1, s.shots());

    s.update(6549, 10.0f, -5.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
    s.update(6550, 10.0f, -5.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
}

void test_burst_is_capped() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 5000, 0, &why));
    s.update(10, 0.0f, 0.0f);    // arrived (already at target)
    s.update(200, 0.0f, 0.0f);   // settle window passed, valve opens now
    TEST_ASSERT_TRUE(s.valveOpen());
    s.update(699, 0.0f, 0.0f);   // 499 ms of a capped 500 ms burst
    TEST_ASSERT_TRUE(s.valveOpen());
    s.update(700, 0.0f, 0.0f);   // 500 ms cap reached
    TEST_ASSERT_FALSE(s.valveOpen());
}

void test_zero_length_burst_is_rejected() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_FALSE(s.request(0.0f, 0.0f, 0, 0, &why));
    TEST_ASSERT_EQUAL_STRING("bad", why);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
}

void test_second_request_is_rejected_while_busy_and_cooling() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 0, &why));

    why = nullptr;
    TEST_ASSERT_FALSE(s.request(0.0f, 0.0f, 300, 10, &why));
    TEST_ASSERT_EQUAL_STRING("busy", why);

    s.update(10, 0.0f, 0.0f);
    s.update(200, 0.0f, 0.0f);
    s.update(500, 0.0f, 0.0f);  // burst done, cooling down
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);

    why = nullptr;
    TEST_ASSERT_FALSE(s.request(0.0f, 0.0f, 300, 600, &why));
    TEST_ASSERT_EQUAL_STRING("cooldown", why);
}

void test_abort_closes_the_valve_immediately() {
    Shooter s;
    const char* why = nullptr;
    s.request(0.0f, 0.0f, 300, 0, &why);
    s.update(10, 0.0f, 0.0f);
    s.update(200, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(s.valveOpen());

    // Water was already leaving the nozzle when this abort happens, so under
    // the new abort() semantics it counts as a shot and starts the cooldown
    // backstop from the abort moment, rather than returning straight to Idle.
    // See the per-state abort tests below for the full behaviour.
    s.abort(250);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
}

void test_abort_in_idle_is_a_noop() {
    Shooter s;
    s.abort(1000);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(0, s.shots());
}

void test_abort_in_move_returns_to_idle_without_counting_a_shot() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(10.0f, 0.0f, 300, 0, &why));
    s.update(50, 0.0f, 0.0f);  // not arrived yet, still Move
    TEST_ASSERT_TRUE(s.state() == ShooterState::Move);

    s.abort(60);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(0, s.shots());

    // nothing was sprayed, so a retry may follow immediately
    why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 61, &why));
}

void test_abort_in_settle_returns_to_idle_without_counting_a_shot() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 0, &why));
    s.update(10, 0.0f, 0.0f);  // arrived -> Settle
    TEST_ASSERT_TRUE(s.state() == ShooterState::Settle);

    s.abort(50);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(0, s.shots());

    why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 51, &why));
}

void test_abort_in_open_counts_shot_and_starts_cooldown_from_abort_moment() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 0, &why));
    s.update(10, 0.0f, 0.0f);   // arrived -> Settle
    s.update(200, 0.0f, 0.0f);  // settle passed -> Open, valve opens
    TEST_ASSERT_TRUE(s.valveOpen());

    s.abort(250);  // 50 ms into the burst, well short of the requested 300 ms
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
    TEST_ASSERT_EQUAL_UINT32(1, s.shots());

    // the cooldown is stamped at the abort time (250), not at when the burst
    // would naturally have ended (500): still cooling at 250+5000-1, over at
    // 250+5000.
    why = nullptr;
    TEST_ASSERT_FALSE(s.request(0.0f, 0.0f, 300, 250 + 5000 - 1, &why));
    TEST_ASSERT_EQUAL_STRING("cooldown", why);
    s.update(250 + 5000 - 1, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);

    s.update(250 + 5000, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 250 + 5000, &why));
}

void test_abort_in_cooldown_preserves_remaining_cooldown() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 0, &why));
    s.update(10, 0.0f, 0.0f);
    s.update(200, 0.0f, 0.0f);  // valve opens
    s.update(500, 0.0f, 0.0f);  // burst completes naturally -> Cooldown stamped at 500
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
    TEST_ASSERT_EQUAL_UINT32(1, s.shots());

    // aborting mid-cooldown must not reset or shorten it
    s.abort(1000);  // 500 ms into the 5000 ms cooldown
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(1, s.shots());  // not double-counted

    // the cooldown clock still runs from the ORIGINAL stamp (500), not from
    // the abort call (1000): still cooling at 500+5000-1=5499, over at 5500.
    why = nullptr;
    TEST_ASSERT_FALSE(s.request(0.0f, 0.0f, 300, 5499, &why));
    TEST_ASSERT_EQUAL_STRING("cooldown", why);
    s.update(5499, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Cooldown);

    s.update(5500, 0.0f, 0.0f);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 5500, &why));
}

void test_move_times_out_after_2000ms() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(10.0f, 0.0f, 300, 0, &why));

    // servo never arrives (always reports 0,0 while the target is 10,0)
    for (Millis t = 100; t < 2000; t += 100) {
        s.update(t, 0.0f, 0.0f);
        TEST_ASSERT_TRUE(s.state() == ShooterState::Move);
        TEST_ASSERT_FALSE(s.valveOpen());
    }

    s.update(2000, 0.0f, 0.0f);  // 2000 ms since the request: timeout reached
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(0, s.shots());

    // nothing was sprayed, so a later request is accepted right away
    why = nullptr;
    TEST_ASSERT_TRUE(s.request(0.0f, 0.0f, 300, 2001, &why));
}

void test_move_with_nan_angles_times_out_instead_of_wedging() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(10.0f, -5.0f, 300, 0, &why));

    const float nan = std::numeric_limits<float>::quiet_NaN();
    s.update(500, nan, nan);
    TEST_ASSERT_TRUE(s.state() == ShooterState::Move);

    s.update(2000, nan, nan);  // NaN never satisfies "arrived"; timeout rescues it
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_EQUAL_UINT32(0, s.shots());
}

void test_move_arriving_just_under_the_timeout_fires_normally() {
    Shooter s;
    const char* why = nullptr;
    TEST_ASSERT_TRUE(s.request(10.0f, 0.0f, 300, 0, &why));

    s.update(1999, 10.0f, 0.0f);  // arrives just under the 2000 ms timeout
    TEST_ASSERT_TRUE(s.state() == ShooterState::Settle);

    s.update(1999 + 150, 10.0f, 0.0f);  // settle passes
    TEST_ASSERT_TRUE(s.state() == ShooterState::Open);
    TEST_ASSERT_TRUE(s.valveOpen());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_full_shot_sequence);
    RUN_TEST(test_burst_is_capped);
    RUN_TEST(test_zero_length_burst_is_rejected);
    RUN_TEST(test_second_request_is_rejected_while_busy_and_cooling);
    RUN_TEST(test_abort_closes_the_valve_immediately);
    RUN_TEST(test_abort_in_idle_is_a_noop);
    RUN_TEST(test_abort_in_move_returns_to_idle_without_counting_a_shot);
    RUN_TEST(test_abort_in_settle_returns_to_idle_without_counting_a_shot);
    RUN_TEST(test_abort_in_open_counts_shot_and_starts_cooldown_from_abort_moment);
    RUN_TEST(test_abort_in_cooldown_preserves_remaining_cooldown);
    RUN_TEST(test_move_times_out_after_2000ms);
    RUN_TEST(test_move_with_nan_angles_times_out_instead_of_wedging);
    RUN_TEST(test_move_arriving_just_under_the_timeout_fires_normally);
    return UNITY_END();
}
