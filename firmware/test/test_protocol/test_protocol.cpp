#include <unity.h>

#include "protocol.h"

using namespace dwarf;

void setUp() {}
void tearDown() {}

void test_parse_heartbeat() {
    Command c = parseCommand("{\"c\":\"hb\"}");
    TEST_ASSERT_TRUE(c.type == CmdType::Hb);
}

void test_parse_arm_true() {
    Command c = parseCommand("{\"c\":\"arm\",\"v\":true}");
    TEST_ASSERT_TRUE(c.type == CmdType::Arm);
    TEST_ASSERT_TRUE(c.flag);
}

void test_parse_aim() {
    Command c = parseCommand("{\"c\":\"aim\",\"pan\":12.5,\"tilt\":-3.0}");
    TEST_ASSERT_TRUE(c.type == CmdType::Aim);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 12.5f, c.pan);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -3.0f, c.tilt);
}

void test_parse_shoot() {
    Command c = parseCommand("{\"c\":\"shoot\",\"pan\":14.0,\"tilt\":-2.5,\"ms\":300}");
    TEST_ASSERT_TRUE(c.type == CmdType::Shoot);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 14.0f, c.pan);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -2.5f, c.tilt);
    TEST_ASSERT_EQUAL_UINT16(300, c.ms);
}

void test_parse_cfg() {
    Command c = parseCommand(
        "{\"c\":\"cfg\",\"panMin\":-45,\"panMax\":45,\"tiltMin\":-20,\"tiltMax\":30}");
    TEST_ASSERT_TRUE(c.type == CmdType::Cfg);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -45.0f, c.panMin);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.0f, c.panMax);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -20.0f, c.tiltMin);
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 30.0f, c.tiltMax);
}

void test_parse_rejects_garbage() {
    TEST_ASSERT_TRUE(parseCommand("not json").type == CmdType::None);
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"nope\"}").type == CmdType::None);
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"arm\"}").type == CmdType::None);
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"shoot\",\"pan\":1.0}").type == CmdType::None);
    TEST_ASSERT_TRUE(parseCommand(nullptr).type == CmdType::None);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_parse_heartbeat);
    RUN_TEST(test_parse_arm_true);
    RUN_TEST(test_parse_aim);
    RUN_TEST(test_parse_shoot);
    RUN_TEST(test_parse_cfg);
    RUN_TEST(test_parse_rejects_garbage);
    return UNITY_END();
}
