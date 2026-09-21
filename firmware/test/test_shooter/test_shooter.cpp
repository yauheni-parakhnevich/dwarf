#include <unity.h>

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

    s.abort();
    TEST_ASSERT_FALSE(s.valveOpen());
    TEST_ASSERT_TRUE(s.state() == ShooterState::Idle);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_full_shot_sequence);
    RUN_TEST(test_burst_is_capped);
    RUN_TEST(test_zero_length_burst_is_rejected);
    RUN_TEST(test_second_request_is_rejected_while_busy_and_cooling);
    RUN_TEST(test_abort_closes_the_valve_immediately);
    return UNITY_END();
}
