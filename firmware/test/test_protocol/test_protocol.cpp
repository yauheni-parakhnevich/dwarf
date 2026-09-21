#include <unity.h>

#include <cstring>

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

void test_parse_rejects_nonfinite() {
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1e400,\"tilt\":0,\"ms\":300}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"aim\",\"pan\":0,\"tilt\":-1e400}").type == CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand(
            "{\"c\":\"cfg\",\"panMin\":-45,\"panMax\":1e400,\"tiltMin\":-20,\"tiltMax\":30}")
            .type == CmdType::None);
}

void test_parse_shoot_ms_bounds() {
    // Rejected: negative, fractional, out of range, wrong type.
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":-1}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":300.7}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":300.0}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":70000}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":\"300\"}").type ==
        CmdType::None);

    // Accepted: valid boundary values.
    Command low = parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":1}");
    TEST_ASSERT_TRUE(low.type == CmdType::Shoot);
    TEST_ASSERT_EQUAL_UINT16(1, low.ms);

    Command high = parseCommand("{\"c\":\"shoot\",\"pan\":1.0,\"tilt\":1.0,\"ms\":65535}");
    TEST_ASSERT_TRUE(high.type == CmdType::Shoot);
    TEST_ASSERT_EQUAL_UINT16(65535, high.ms);
}

void test_fault_name() {
    TEST_ASSERT_EQUAL_STRING("TANK_EMPTY", faultName(Fault::TankEmpty));
    TEST_ASSERT_EQUAL_STRING("OVERTEMP", faultName(Fault::Overtemp));
    TEST_ASSERT_EQUAL_STRING("", faultName(Fault::None));
}

void test_parse_rejects_wrong_type_present() {
    TEST_ASSERT_TRUE(
        parseCommand("{\"c\":\"shoot\",\"pan\":\"x\",\"tilt\":1,\"ms\":300}").type ==
        CmdType::None);
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"arm\",\"v\":1}").type == CmdType::None);
}

void test_parse_park_charge_fan() {
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"park\"}").type == CmdType::Park);

    Command chargeOff = parseCommand("{\"c\":\"charge\",\"v\":false}");
    TEST_ASSERT_TRUE(chargeOff.type == CmdType::Charge);
    TEST_ASSERT_FALSE(chargeOff.flag);

    Command fanOn = parseCommand("{\"c\":\"fan\",\"v\":true}");
    TEST_ASSERT_TRUE(fanOn.type == CmdType::Fan);
    TEST_ASSERT_TRUE(fanOn.flag);

    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"charge\"}").type == CmdType::None);
    TEST_ASSERT_TRUE(parseCommand("{\"c\":\"fan\"}").type == CmdType::None);
}

void test_format_status() {
    Status s;
    s.armed = true;
    s.pan = 12.5f;
    s.tilt = -3.0f;
    s.tankOk = true;
    s.pump = true;
    s.charge = false;
    s.fan = false;
    s.temp = 31.25f;
    s.fault = Fault::None;
    s.shots = 12;

    char buf[256];
    const size_t n = formatStatus(s, buf, sizeof(buf));

    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"armed\":true,\"pan\":12.5,\"tilt\":-3,\"tank\":\"ok\",\"pump\":true,"
        "\"charge\":false,\"fan\":false,\"temp\":31.3,\"fault\":null,\"shots\":12}",
        buf);
}

void test_format_status_with_fault() {
    Status s;
    s.tankOk = false;
    s.fault = Fault::TankEmpty;

    char buf[256];
    formatStatus(s, buf, sizeof(buf));

    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"tank\":\"low\""));
    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"fault\":\"TANK_EMPTY\""));
}

void test_format_ack() {
    char buf[128];

    formatAck("shoot", false, "cooldown", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}", buf);

    formatAck("arm", true, nullptr, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("{\"ack\":\"arm\",\"ok\":true}", buf);
}

void test_status_fits_in_one_ble_message() {
    Status s;
    s.armed = true;
    s.pan = -59.9f;
    s.tilt = -29.9f;
    s.temp = -10.5f;
    s.fault = Fault::Overtemp;
    s.shots = 4294967295u;

    char buf[256];
    const size_t n = formatStatus(s, buf, sizeof(buf));

    TEST_ASSERT_TRUE(n <= 180);  // BLE MTU budget from the spec
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_parse_heartbeat);
    RUN_TEST(test_parse_arm_true);
    RUN_TEST(test_parse_aim);
    RUN_TEST(test_parse_shoot);
    RUN_TEST(test_parse_cfg);
    RUN_TEST(test_parse_rejects_garbage);
    RUN_TEST(test_parse_rejects_nonfinite);
    RUN_TEST(test_parse_shoot_ms_bounds);
    RUN_TEST(test_fault_name);
    RUN_TEST(test_parse_rejects_wrong_type_present);
    RUN_TEST(test_parse_park_charge_fan);
    RUN_TEST(test_format_status);
    RUN_TEST(test_format_status_with_fault);
    RUN_TEST(test_format_ack);
    RUN_TEST(test_status_fits_in_one_ble_message);
    return UNITY_END();
}
