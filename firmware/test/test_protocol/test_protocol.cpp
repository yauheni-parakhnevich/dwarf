#include <unity.h>

#include <cstring>
#include <limits>

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
    // Every field pushed to its longest simultaneous serialisation: "false" (not
    // "true"), "low" tank, all outputs off, the longer fault name (TANK_EMPTY is
    // longer than OVERTEMP), shots at UINT32_MAX, and pan/tilt/temp at their widest
    // rendered values given one-decimal rounding and the servo/sensor limits.
    Status s;
    s.armed = false;
    s.pan = -59.9f;
    s.tilt = -29.9f;
    s.tankOk = false;
    s.pump = false;
    s.charge = false;
    s.fan = false;
    s.temp = -127.5f;
    s.fault = Fault::TankEmpty;
    s.shots = 4294967295u;

    char buf[256];
    const size_t n = formatStatus(s, buf, sizeof(buf));

    TEST_ASSERT_TRUE(n > 0);  // must not have been silently truncated to empty
    TEST_ASSERT_EQUAL_UINT(n, std::strlen(buf));
    TEST_ASSERT_TRUE(n <= 180);  // BLE MTU budget from the spec
}

void test_ack_fits_in_one_ble_message() {
    // Longest command name ("charge") and longest why code ("disarmed"/"cooldown",
    // both 8 characters; see the plan's section 7 list of why codes).
    char buf[128];
    const size_t n = formatAck("charge", false, "disarmed", buf, sizeof(buf));

    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_EQUAL_UINT(n, std::strlen(buf));
    TEST_ASSERT_TRUE(n <= 180);  // BLE MTU budget from the spec
}

void test_format_status_truncation_returns_empty() {
    Status s;
    s.armed = true;
    s.pan = 12.5f;
    s.tilt = -3.0f;
    s.fault = Fault::None;
    s.shots = 12;

    char buf[32];  // far too small for a full status object
    std::memset(buf, 'X', sizeof(buf));
    const size_t n = formatStatus(s, buf, sizeof(buf));

    TEST_ASSERT_EQUAL_UINT(0, n);
    TEST_ASSERT_EQUAL_STRING("", buf);
}

void test_format_ack_truncation_returns_empty() {
    char buf[8];  // far too small for a full ack object
    std::memset(buf, 'X', sizeof(buf));
    const size_t n = formatAck("shoot", false, "cooldown", buf, sizeof(buf));

    TEST_ASSERT_EQUAL_UINT(0, n);
    TEST_ASSERT_EQUAL_STRING("", buf);
}

void test_format_status_exact_fit_boundary() {
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

    char full[256];
    const size_t n = formatStatus(s, full, sizeof(full));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_EQUAL_UINT(n, std::strlen(full));  // property the Arduino layer relies on

    // Exactly enough room (content + NUL): must succeed and match byte-for-byte.
    char exact[256];
    const size_t nExact = formatStatus(s, exact, n + 1);
    TEST_ASSERT_EQUAL_UINT(n, nExact);
    TEST_ASSERT_EQUAL_STRING(full, exact);

    // One byte short of that: no room for the NUL, must be reported as failure.
    char short_[256];
    std::memset(short_, 'X', sizeof(short_));
    const size_t nShort = formatStatus(s, short_, n);
    TEST_ASSERT_EQUAL_UINT(0, nShort);
    TEST_ASSERT_EQUAL_STRING("", short_);
}

void test_format_ack_exact_fit_boundary() {
    char full[128];
    const size_t n = formatAck("shoot", false, "cooldown", full, sizeof(full));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_EQUAL_UINT(n, std::strlen(full));

    char exact[128];
    const size_t nExact = formatAck("shoot", false, "cooldown", exact, n + 1);
    TEST_ASSERT_EQUAL_UINT(n, nExact);
    TEST_ASSERT_EQUAL_STRING(full, exact);

    char short_[128];
    std::memset(short_, 'X', sizeof(short_));
    const size_t nShort = formatAck("shoot", false, "cooldown", short_, n);
    TEST_ASSERT_EQUAL_UINT(0, nShort);
    TEST_ASSERT_EQUAL_STRING("", short_);
}

void test_format_status_nonfinite_and_sentinel_temp() {
    Status s;
    char buf[256];

    // NaN and +/-infinity are not valid JSON tokens; this project's ArduinoJson
    // configuration is expected to serialise them as null.
    s.temp = std::numeric_limits<float>::quiet_NaN();
    size_t n = formatStatus(s, buf, sizeof(buf));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"temp\":null"));

    s.temp = std::numeric_limits<float>::infinity();
    n = formatStatus(s, buf, sizeof(buf));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"temp\":null"));

    s.temp = -std::numeric_limits<float>::infinity();
    n = formatStatus(s, buf, sizeof(buf));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"temp\":null"));

    // -127 is the DS18B20 "no sensor" sentinel: an ordinary (finite) number, so it
    // must pass through unchanged, not be mistaken for a non-finite value.
    s.temp = -127.0f;
    n = formatStatus(s, buf, sizeof(buf));
    TEST_ASSERT_TRUE(n > 0);
    TEST_ASSERT_NOT_NULL(std::strstr(buf, "\"temp\":-127"));
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
    RUN_TEST(test_ack_fits_in_one_ble_message);
    RUN_TEST(test_format_status_truncation_returns_empty);
    RUN_TEST(test_format_ack_truncation_returns_empty);
    RUN_TEST(test_format_status_exact_fit_boundary);
    RUN_TEST(test_format_ack_exact_fit_boundary);
    RUN_TEST(test_format_status_nonfinite_and_sentinel_temp);
    return UNITY_END();
}
