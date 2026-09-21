# ESP32 Firmware + Bench Rig Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ESP32 firmware that aims the gnome's head and fires timed water bursts on command over BLE, with its own safety limits, verified by native unit tests and a bench rig that sprays into a bucket.

**Architecture:** All decision logic lives in `firmware/lib/dwarf/`, a plain C++17 library with no Arduino headers, so it compiles and runs under `pio test -e native` on the Mac. Time is never read inside the library: every entry point takes a `now` in milliseconds, which makes the state machines testable with a fake clock. The Arduino layer in `firmware/src/` only moves bytes: it reads sensors, calls `Controller::update()`, writes GPIO and servo pulses, and shuttles JSON between BLE and the library.

**Tech Stack:** PlatformIO, Arduino framework for ESP32, NimBLE-Arduino 1.4.x (BLE server), ArduinoJson 7 (messages, works natively too), ESP32Servo (50 Hz PWM), DallasTemperature + OneWire (DS18B20), Unity (tests bundled with PlatformIO).

**Spec:** `docs/superpowers/specs/2026-09-18-dwarf-cat-deterrent-design.md`, sections 4, 6, 7 and milestone M1 in section 12.

---

## File Structure

| File | Responsibility |
|---|---|
| `firmware/platformio.ini` | Two build environments: `esp32dev` (hardware) and `native` (tests) |
| `firmware/lib/dwarf/types.h` | Shared value types: `Command`, `Status`, `Limits`, `Fault`, `Millis` |
| `firmware/lib/dwarf/protocol.h/.cpp` | JSON in and out: `parseCommand`, `formatStatus`, `formatAck` |
| `firmware/lib/dwarf/servo.h/.cpp` | Pure math: angle clamping, angle→microseconds, slew limiting |
| `firmware/lib/dwarf/shooter.h/.cpp` | Shot state machine: move → settle → open → close → cooldown |
| `firmware/lib/dwarf/controller.h/.cpp` | Owns arm state, limits, faults, heartbeat, pump/fan/charger rules; drives `Shooter` |
| `firmware/test/test_fixtures.h` | Generated from `protocol/fixtures/`; canonical messages for tests |
| `firmware/src/pins.h` | Board pin map |
| `firmware/src/main.cpp` | Arduino setup/loop: sensors, servos, GPIO, BLE, watchdog |
| `firmware/test/test_protocol/test_protocol.cpp` | Parser and formatter tests |
| `firmware/test/test_servo/test_servo.cpp` | Servo math tests |
| `firmware/test/test_shooter/test_shooter.cpp` | Shot state machine tests |
| `firmware/test/test_controller/test_controller.cpp` | Controller rule tests, including a full message sequence |
| `protocol/fixtures/*.json` | Canonical messages shared with the future Swift test suite |
| `tools/gen_fixtures.py` | Turns `protocol/fixtures/*.json` into `test_fixtures.h` |
| `hardware/bench-checklist.md` | Manual bench test procedure and results table |

**Dependency direction:** `main.cpp` → `controller` → {`shooter`, `servo`, `protocol`} → `types.h`. Nothing in `lib/dwarf/` includes anything from `src/`.

---

### Task 0: Project scaffold

**Files:**
- Create: `firmware/platformio.ini`
- Create: `firmware/lib/dwarf/types.h`
- Create: `.gitignore`

- [ ] **Step 1: Install PlatformIO if missing**

Run: `pio --version`
Expected: a version like `PlatformIO Core, version 6.1.16`. If the command is not found, install it:

```bash
brew install platformio
```

- [ ] **Step 2: Create the PlatformIO config**

Create `firmware/platformio.ini`:

```ini
[env]
lib_deps = bblanchon/ArduinoJson@^7.2.0
build_flags = -std=gnu++17

[env:esp32dev]
platform = espressif32@^6.9.0
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
    ${env.lib_deps}
    h2zero/NimBLE-Arduino@^1.4.2
    madhephaestus/ESP32Servo@^3.0.5
    milesburton/DallasTemperature@^3.11.0
    paulstoffregen/OneWire@^2.3.8

[env:native]
platform = native
test_framework = unity
build_src_filter = -<*>
build_flags =
    ${env.build_flags}
    -DDWARF_NATIVE
    -Wall
    -Wextra
```

Notes for the engineer:
- `build_src_filter = -<*>` keeps the native build from compiling `src/main.cpp`, which needs Arduino headers.
- NimBLE is pinned to 1.4.x on purpose: 2.x changed the characteristic callback signature used in Task 11.
- ArduinoJson is declared in `[env]` so both environments get it. It is a plain C++ library and builds on the Mac.

- [ ] **Step 3: Create the shared types**

Create `firmware/lib/dwarf/types.h`:

```cpp
#pragma once
#include <cstdint>

namespace dwarf {

using Millis = uint32_t;

enum class CmdType { None, Hb, Arm, Aim, Park, Shoot, Charge, Fan, Cfg };

struct Command {
    CmdType type = CmdType::None;
    bool flag = false;   // arm / charge / fan value
    float pan = 0.0f;    // aim / shoot
    float tilt = 0.0f;   // aim / shoot
    uint16_t ms = 0;     // shoot burst length
    float panMin = 0.0f; // cfg
    float panMax = 0.0f;
    float tiltMin = 0.0f;
    float tiltMax = 0.0f;
};

struct Limits {
    float panMin = -60.0f;
    float panMax = 60.0f;
    float tiltMin = -30.0f;
    float tiltMax = 40.0f;
};

enum class Fault { None, TankEmpty, Overtemp };

struct Status {
    bool armed = false;         // pump powered and shots allowed
    float pan = 0.0f;           // degrees from park, positive right
    float tilt = 0.0f;          // degrees from park, positive up
    bool tankOk = true;         // float switch reports water in the tank
    bool pump = false;          // pump output state
    bool charge = true;         // iPhone charger switch enabled
    bool fan = false;           // fan output state
    float temp = 0.0f;          // dry-zone temperature, degrees Celsius
    Fault fault = Fault::None;
    uint32_t shots = 0;         // shots fired since boot
};

}  // namespace dwarf
```

- [ ] **Step 4: Create .gitignore**

Create `.gitignore` in the repository root:

```gitignore
.pio/
.vscode/
*.pdf
.DS_Store
```

- [ ] **Step 5: Verify the config parses**

Run: `cd firmware && pio project config`
Expected: all three sections are printed. Check that `env:native` shows `platform = native`, `test_framework = unity`, and `build_flags` containing `-std=gnu++17 -DDWARF_NATIVE -Wall -Wextra`, and that `env:esp32dev` lists all five libraries. (`pio project config` takes no `-e` option in PlatformIO 6.2.)

Do not run `pio run -e native` yet. At this point it fails with `Error: Nothing to build`, because `build_src_filter` excludes `src/` and the only file under `lib/dwarf/` is a header. PlatformIO 6.2 treats "no compilable sources" as an error rather than a warning. The native environment first compiles something real in Task 1, where `pio test -e native -f test_protocol` is the check.

- [ ] **Step 6: Commit**

```bash
git add .gitignore firmware/platformio.ini firmware/lib/dwarf/types.h
git commit -m "build: add PlatformIO project skeleton and shared firmware types"
```

---

### Task 1: Command parser

**Files:**
- Create: `firmware/lib/dwarf/protocol.h`
- Create: `firmware/lib/dwarf/protocol.cpp`
- Test: `firmware/test/test_protocol/test_protocol.cpp`

- [ ] **Step 1: Write the failing test**

Create `firmware/test/test_protocol/test_protocol.cpp`:

```cpp
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
```

Design note worth understanding: a command missing a required field is rejected as `CmdType::None` rather than silently defaulted. A dropped BLE field must never turn into a shot at angle 0.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd firmware && pio test -e native -f test_protocol`
Expected: compilation failure, `protocol.h: No such file or directory`.

- [ ] **Step 3: Write the header**

Create `firmware/lib/dwarf/protocol.h`:

```cpp
#pragma once
#include <cstddef>

#include "types.h"

namespace dwarf {

// Parses one JSON command object. A malformed message, an unknown command name
// or a missing required field all yield a Command whose type is CmdType::None.
Command parseCommand(const char* json);

// Serialises a status object. Returns the number of bytes written.
size_t formatStatus(const Status& s, char* out, size_t cap);

// Serialises an acknowledgement. `why` is written only when ok is false.
size_t formatAck(const char* cmd, bool ok, const char* why, char* out, size_t cap);

// "TANK_EMPTY", "OVERTEMP", or "" for Fault::None.
const char* faultName(Fault f);

}  // namespace dwarf
```

- [ ] **Step 4: Write the parser**

Create `firmware/lib/dwarf/protocol.cpp`:

```cpp
#include "protocol.h"

#include <ArduinoJson.h>

#include <cmath>
#include <cstring>

namespace dwarf {
namespace {

CmdType typeFromName(const char* name) {
    if (name == nullptr) return CmdType::None;
    if (std::strcmp(name, "hb") == 0) return CmdType::Hb;
    if (std::strcmp(name, "arm") == 0) return CmdType::Arm;
    if (std::strcmp(name, "aim") == 0) return CmdType::Aim;
    if (std::strcmp(name, "park") == 0) return CmdType::Park;
    if (std::strcmp(name, "shoot") == 0) return CmdType::Shoot;
    if (std::strcmp(name, "charge") == 0) return CmdType::Charge;
    if (std::strcmp(name, "fan") == 0) return CmdType::Fan;
    if (std::strcmp(name, "cfg") == 0) return CmdType::Cfg;
    return CmdType::None;
}

}  // namespace

Command parseCommand(const char* json) {
    Command c;
    if (json == nullptr) return c;

    JsonDocument doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) return c;

    const CmdType t = typeFromName(doc["c"]);
    switch (t) {
        case CmdType::None:
            return c;
        case CmdType::Hb:
        case CmdType::Park:
            break;
        case CmdType::Arm:
        case CmdType::Charge:
        case CmdType::Fan:
            if (!doc["v"].is<bool>()) return c;
            c.flag = doc["v"].as<bool>();
            break;
        case CmdType::Aim:
            if (!doc["pan"].is<float>() || !doc["tilt"].is<float>()) return c;
            c.pan = doc["pan"].as<float>();
            c.tilt = doc["tilt"].as<float>();
            break;
        case CmdType::Shoot:
            if (!doc["pan"].is<float>() || !doc["tilt"].is<float>() ||
                !doc["ms"].is<uint16_t>()) {
                return c;
            }
            c.pan = doc["pan"].as<float>();
            c.tilt = doc["tilt"].as<float>();
            c.ms = doc["ms"].as<uint16_t>();
            break;
        case CmdType::Cfg:
            if (!doc["panMin"].is<float>() || !doc["panMax"].is<float>() ||
                !doc["tiltMin"].is<float>() || !doc["tiltMax"].is<float>()) {
                return c;
            }
            c.panMin = doc["panMin"].as<float>();
            c.panMax = doc["panMax"].as<float>();
            c.tiltMin = doc["tiltMin"].as<float>();
            c.tiltMax = doc["tiltMax"].as<float>();
            break;
    }

    c.type = t;
    return c;
}

const char* faultName(Fault f) {
    switch (f) {
        case Fault::TankEmpty:
            return "TANK_EMPTY";
        case Fault::Overtemp:
            return "OVERTEMP";
        case Fault::None:
        default:
            return "";
    }
}

}  // namespace dwarf
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd firmware && pio test -e native -f test_protocol`
Expected: `6 Tests 0 Failures 0 Ignored` and `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/dwarf/protocol.h firmware/lib/dwarf/protocol.cpp firmware/test/test_protocol/test_protocol.cpp
git commit -m "feat(firmware): parse BLE JSON commands"
```


**Post-review addendum (applied in commit `209ce5b`):** code quality review of this task
produced three accepted changes, which are already in the committed files:

1. `parseCommand` also rejects non-finite floats. ArduinoJson's `is<float>()` is true for a
   number that overflowed to infinity while parsing, so `1e400` is valid JSON that yields
   `+inf`. A `cfg` carrying `panMax = +inf` would pass the controller's ordering check and
   silently widen the aim limits. Every parsed angle now goes through `std::isfinite`, and a
   non-finite value is rejected exactly like a missing field.
2. `faultName` lost its `default:` label, so a future `Fault` enumerator becomes a
   `-Wswitch` warning instead of silently serialising as `""`.
3. Five test groups were added: non-finite rejection, `ms` bounds (negative, fractional,
   over-range, string), `faultName` return values, wrong-type-but-present keys, and the
   previously untested `park`, `charge` and `fan` commands. The suite is 11 tests.

Two review suggestions were declined: adding a reason code or raw command name to rejected
messages (BLE writes are sequential and each gets one ack, so the phone already knows which
command was rejected), and removing the redundant `case CmdType::None: return c;`.

---

### Task 2: Status and ack formatting

**Files:**
- Modify: `firmware/lib/dwarf/protocol.cpp` (append two functions)
- Modify: `firmware/test/test_protocol/test_protocol.cpp` (append tests and RUN_TEST lines)

- [ ] **Step 1: Write the failing tests**

In `firmware/test/test_protocol/test_protocol.cpp`, add these functions above `main`:

```cpp
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
```

Add `#include <cstring>` at the top of the test file, and add these lines to `main` before `return UNITY_END();`:

```cpp
    RUN_TEST(test_format_status);
    RUN_TEST(test_format_status_with_fault);
    RUN_TEST(test_format_ack);
    RUN_TEST(test_status_fits_in_one_ble_message);
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd firmware && pio test -e native -f test_protocol`
Expected: link error, `undefined reference to dwarf::formatStatus`.

- [ ] **Step 3: Implement the formatters**

In `firmware/lib/dwarf/protocol.cpp`, add above `faultName`:

```cpp
namespace {

// One decimal place keeps the message inside the BLE MTU budget and matches the
// precision the servos can actually deliver.
float round1(float v) { return std::round(v * 10.0f) / 10.0f; }

}  // namespace

size_t formatStatus(const Status& s, char* out, size_t cap) {
    JsonDocument doc;
    doc["armed"] = s.armed;
    doc["pan"] = round1(s.pan);
    doc["tilt"] = round1(s.tilt);
    doc["tank"] = s.tankOk ? "ok" : "low";
    doc["pump"] = s.pump;
    doc["charge"] = s.charge;
    doc["fan"] = s.fan;
    doc["temp"] = round1(s.temp);
    if (s.fault == Fault::None) {
        doc["fault"] = nullptr;
    } else {
        doc["fault"] = faultName(s.fault);
    }
    doc["shots"] = s.shots;
    return serializeJson(doc, out, cap);
}

size_t formatAck(const char* cmd, bool ok, const char* why, char* out, size_t cap) {
    JsonDocument doc;
    doc["ack"] = cmd;
    doc["ok"] = ok;
    if (!ok && why != nullptr) doc["why"] = why;
    return serializeJson(doc, out, cap);
}
```

Note: this block uses an anonymous namespace that already exists higher in the file for `typeFromName`. Opening a second anonymous namespace in the same file is legal C++ and keeps `round1` file-local.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd firmware && pio test -e native -f test_protocol`
Expected: `15 Tests 0 Failures 0 Ignored` (11 from Task 1 plus the 4 added here).

If `test_format_status` fails on the `tilt` field, check the expected string: ArduinoJson prints `-3.0f` as `-3`, not `-3.0`. Match the library's output rather than changing the library.

- [ ] **Step 5: Commit**

```bash
git add firmware/lib/dwarf/protocol.cpp firmware/test/test_protocol/test_protocol.cpp
git commit -m "feat(firmware): format status and ack messages"
```

**Post-review addendum (applied in commit `c9d9624`):** code quality review produced four
accepted changes, already in the committed files:

1. **Truncation is now detectable.** `serializeJson` clamps to `cap` and returns
   `min(needed, cap)`, and it writes no NUL terminator on an exact fit, so a caller could
   neither detect a cut-off message nor safely `strlen` the buffer. A private `writeJson`
   helper now wraps it: `cap == 0` or a null `out` returns 0, `n >= cap` writes an empty
   string and returns 0, and success NUL-terminates and returns `n == strlen(out)`. Both
   formatters go through it. The header documents the contract. The pre-fix test run
   crashed with SIGILL while `strcmp`-ing an unterminated buffer, which is what this
   prevents.
2. **Truncation tests**, including the exact-fit boundary: `cap == n` fails, `cap == n + 1`
   succeeds byte-for-byte.
3. **The budget test is now the true worst case**: every field at its longest rendering at
   once (`armed:false`, `tank:"low"`, all outputs false, `fault:"TANK_EMPTY"`,
   `shots:4294967295`, `pan:-59.9`, `tilt:-29.9`, `temp:-127.5`). Measured at **147 bytes**
   against the 180-byte budget. An ack worst case measures 44 bytes.
4. **Non-finite and sensor-sentinel behaviour is pinned**: NaN and ±infinity serialise as
   `null`, and -127.0 (the DS18B20 "no sensor" value) passes through as `-127`. The test
   exists so that a library upgrade flipping `ARDUINOJSON_ENABLE_NAN` cannot silently start
   emitting bare `NaN` tokens, which are not valid JSON.

Declined: reusing one `JsonDocument` or supplying a custom allocator (one malloc/free of
the same size per second does not meaningfully fragment a heap, since identical-size blocks
get reused), and asserting on a null `cmd` in `formatAck` (every caller passes a literal).

The suite is 21 tests after this task.

---

### Task 3: Shared protocol fixtures

**Files:**
- Create: `protocol/fixtures/commands.json`
- Create: `protocol/fixtures/status.json`
- Create: `tools/gen_fixtures.py`
- Create: `firmware/test/test_fixtures.h` (generated, committed)
- Modify: `firmware/test/test_protocol/test_protocol.cpp`

Why this exists: the iOS app and the firmware must agree on every byte. Both test suites read the same fixture files, so a change on one side that breaks the other fails a test instead of failing in the yard.

- [ ] **Step 1: Write the fixture files**

Create `protocol/fixtures/commands.json`:

```json
{
  "hb": "{\"c\":\"hb\"}",
  "arm_on": "{\"c\":\"arm\",\"v\":true}",
  "arm_off": "{\"c\":\"arm\",\"v\":false}",
  "aim": "{\"c\":\"aim\",\"pan\":12.5,\"tilt\":-3.0}",
  "park": "{\"c\":\"park\"}",
  "shoot": "{\"c\":\"shoot\",\"pan\":14.0,\"tilt\":-2.5,\"ms\":300}",
  "charge_off": "{\"c\":\"charge\",\"v\":false}",
  "fan_on": "{\"c\":\"fan\",\"v\":true}",
  "cfg": "{\"c\":\"cfg\",\"panMin\":-60,\"panMax\":60,\"tiltMin\":-30,\"tiltMax\":40}"
}
```

Create `protocol/fixtures/status.json`:

```json
{
  "idle": "{\"armed\":false,\"pan\":0,\"tilt\":0,\"tank\":\"ok\",\"pump\":false,\"charge\":true,\"fan\":false,\"temp\":21.5,\"fault\":null,\"shots\":0}",
  "armed_shooting": "{\"armed\":true,\"pan\":12.5,\"tilt\":-3,\"tank\":\"ok\",\"pump\":true,\"charge\":false,\"fan\":false,\"temp\":31.3,\"fault\":null,\"shots\":12}",
  "tank_empty": "{\"armed\":false,\"pan\":0,\"tilt\":0,\"tank\":\"low\",\"pump\":false,\"charge\":true,\"fan\":false,\"temp\":24,\"fault\":\"TANK_EMPTY\",\"shots\":3}",
  "ack_reject": "{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}"
}
```

- [ ] **Step 2: Write the generator**

Create `tools/gen_fixtures.py`:

```python
#!/usr/bin/env python3
"""Generate a C++ header of canonical protocol messages from protocol/fixtures/.

Run from the repository root:
    python3 tools/gen_fixtures.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "protocol" / "fixtures"
OUT = ROOT / "firmware" / "test" / "test_fixtures.h"


def cpp_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def emit_group(name: str, mapping: dict) -> str:
    rows = ",\n".join(
        f'    {{"{key}", "{cpp_escape(value)}"}}' for key, value in mapping.items()
    )
    return (
        f"inline constexpr Fixture k{name}[] = {{\n{rows}\n}};\n"
        f"inline constexpr int k{name}Count = {len(mapping)};\n"
    )


def main() -> None:
    commands = json.loads((FIXTURES / "commands.json").read_text())
    status = json.loads((FIXTURES / "status.json").read_text())

    body = [
        "// Generated by tools/gen_fixtures.py. Do not edit by hand.",
        "#pragma once",
        "",
        "namespace dwarf {",
        "namespace fixtures {",
        "",
        "struct Fixture {",
        "    const char* name;",
        "    const char* json;",
        "};",
        "",
        emit_group("Commands", commands),
        emit_group("Status", status),
        "}  // namespace fixtures",
        "}  // namespace dwarf",
        "",
    ]
    OUT.write_text("\n".join(body))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(commands)} commands, {len(status)} status")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the generator**

Run: `cd /Users/Yauheni_Parakhnevich/Workspace/dwarf && python3 tools/gen_fixtures.py`
Expected: `wrote firmware/test/test_fixtures.h: 9 commands, 4 status`

- [ ] **Step 4: Write the failing test**

In `firmware/test/test_protocol/test_protocol.cpp`, add `#include "test_fixtures.h"` below the `protocol.h` include, add this test above `main`:

```cpp
void test_every_command_fixture_parses() {
    for (int i = 0; i < fixtures::kCommandsCount; ++i) {
        const fixtures::Fixture& f = fixtures::kCommands[i];
        Command c = parseCommand(f.json);
        TEST_ASSERT_TRUE_MESSAGE(c.type != CmdType::None, f.name);
    }
}

void test_status_fixture_roundtrips() {
    Status s;
    s.armed = true;
    s.pan = 12.5f;
    s.tilt = -3.0f;
    s.pump = true;
    s.charge = false;
    s.temp = 31.3f;
    s.shots = 12;

    char buf[256];
    formatStatus(s, buf, sizeof(buf));

    const char* expected = nullptr;
    for (int i = 0; i < fixtures::kStatusCount; ++i) {
        if (std::strcmp(fixtures::kStatus[i].name, "armed_shooting") == 0) {
            expected = fixtures::kStatus[i].json;
        }
    }
    TEST_ASSERT_NOT_NULL(expected);
    TEST_ASSERT_EQUAL_STRING(expected, buf);
}
```

Add to `main`:

```cpp
    RUN_TEST(test_every_command_fixture_parses);
    RUN_TEST(test_status_fixture_roundtrips);
```

- [ ] **Step 5: Run the tests**

Run: `cd firmware && pio test -e native -f test_protocol`
Expected: `23 Tests 0 Failures 0 Ignored` (21 from Tasks 1–2 plus the 2 added here). If `test_status_fixture_roundtrips` fails, the fixture and the formatter disagree; fix `protocol/fixtures/status.json` to match the formatter's real output, then re-run the generator.

- [ ] **Step 6: Commit**

```bash
git add protocol/fixtures tools/gen_fixtures.py firmware/test/test_fixtures.h firmware/test/test_protocol/test_protocol.cpp
git commit -m "test(protocol): add shared message fixtures and generator"
```

**Post-review addendum (applied in commit `0e16b54`):** review of this task found a
demonstrated build-breaking bug plus several contract gaps. Six accepted changes, already
in the committed files:

1. **`cpp_escape` mangled control characters.** It escaped only backslash and quote, so a
   fixture containing a newline or tab emitted a raw control byte inside a C++ string
   literal and the generated header failed to compile (`missing terminating '"'
   character`). It now escapes `\n`, `\r`, `\t` and emits any other character below
   0x20, or 0x7F, as a **three-digit** octal escape — three digits because a shorter escape
   followed by an ASCII digit would be misparsed. `\uXXXX` is not used: C++ forbids
   universal character names below 0xA0. Non-ASCII UTF-8 passes through untouched.
2. **The generated header moved** from `firmware/lib/dwarf/` to `firmware/test/`, so
   test-only content no longer sits beside the production library sources. The include in
   the test file is now `#include "../test_fixtures.h"`. PlatformIO still discovers only
   the real suites.
3. **Two missing wire shapes added** to `status.json`, both generated from the real
   formatter: `ack_ok` (`{"ack":"arm","ok":true}`, the optional-field-absent shape the iOS
   decoder must handle) and `overtemp` (the other of the two fault codes).
4. **Every status and ack fixture is now regression-tested**, not just `armed_shooting`.
   Hand-editing any fixture fails a test.
5. **`python3 tools/gen_fixtures.py --check`** re-renders in memory and exits non-zero on
   drift without writing, so a fixture edit that skips regeneration is detectable. There is
   no CI in this repo, so this is a manual guard.
6. **Command fixtures assert real values**, not merely that they parse, which catches a
   transposed `pan`/`tilt` or a typo'd limit.

Declined: fixtures for the remaining `why` codes (string variations of a shape already
covered) and any CI or git-hook configuration.

The suite is 24 tests after this task.

**Correction applied during implementation (commit `c679491`):** the `tank_empty` fixture
above originally read `"temp":24.0`. ArduinoJson renders a whole-number float without the
trailing `.0`, the same way it renders `-3.0f` as `-3`, so the real formatter output is
`"temp":24`. The fixture text above has been corrected to match. The other three fixtures
were verified byte-for-byte against the real formatter and needed no change. The suite is
23 tests after this task.

---

### Task 4: Servo math

**Files:**
- Create: `firmware/lib/dwarf/servo.h`
- Create: `firmware/lib/dwarf/servo.cpp`
- Test: `firmware/test/test_servo/test_servo.cpp`

- [ ] **Step 1: Write the failing test**

Create `firmware/test/test_servo/test_servo.cpp`:

```cpp
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd firmware && pio test -e native -f test_servo`
Expected: `servo.h: No such file or directory`.

- [ ] **Step 3: Write the implementation**

Create `firmware/lib/dwarf/servo.h`:

```cpp
#pragma once
#include <cstdint>

namespace dwarf {

// Constrains v to [lo, hi].
float clampf(float v, float lo, float hi);

// Maps -90..+90 degrees to a 500..2500 us servo pulse, plus a per-servo trim in
// microseconds, saturating at the pulse limits.
uint16_t angleToMicros(float angleDeg, float trimUs = 0.0f);

// Moves current toward target by at most degPerSec * dtMs, so the head turns
// smoothly instead of snapping and shaking the gnome.
float slewToward(float current, float target, float degPerSec, uint32_t dtMs);

}  // namespace dwarf
```

Create `firmware/lib/dwarf/servo.cpp`:

```cpp
#include "servo.h"

#include <cmath>

namespace dwarf {

float clampf(float v, float lo, float hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

uint16_t angleToMicros(float angleDeg, float trimUs) {
    const float us = 1500.0f + angleDeg * (1000.0f / 90.0f) + trimUs;
    return static_cast<uint16_t>(std::lround(clampf(us, 500.0f, 2500.0f)));
}

float slewToward(float current, float target, float degPerSec, uint32_t dtMs) {
    const float step = degPerSec * (static_cast<float>(dtMs) / 1000.0f);
    const float delta = target - current;
    if (std::fabs(delta) <= step) return target;
    return current + (delta > 0.0f ? step : -step);
}

}  // namespace dwarf
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd firmware && pio test -e native -f test_servo`
Expected: `6 Tests 0 Failures 0 Ignored`.

- [ ] **Step 5: Commit**

```bash
git add firmware/lib/dwarf/servo.h firmware/lib/dwarf/servo.cpp firmware/test/test_servo/test_servo.cpp
git commit -m "feat(firmware): add servo angle and slew math"
```

**Post-review addendum (applied in commit `bf94eea`):** the implementer's hostile-input
analysis found two real holes, now guarded and tested:

1. **NaN defeated the clamp.** Every comparison with NaN is false, so `clampf` returned it
   unchanged and `std::lround(NaN)` — undefined behaviour — silently produced a pulse of 0;
   the pre-guard test run aborted with SIGABRT. `angleToMicros` now treats a non-finite
   angle or trim as 0, so the head centres instead of receiving a garbage pulse width. Note
   the consequence: ±infinity now centres rather than saturating to 500/2500 µs.
2. **A negative `degPerSec` drove the head away from the target forever.** `slewToward` now
   uses the magnitude of the rate, so a sign error in configuration cannot invert the
   motion.
3. **Non-finite angles in `slewToward`** are handled explicitly: a non-finite target is
   ignored (return `current`), a non-finite `current` heals toward a finite target, and
   both non-finite returns 0, the park angle. Previously a NaN `current` poisoned every
   later call.

Declined: guarding an infinite `degPerSec` (with the magnitude applied it degrades to
"snap to target", same as a large `dtMs`, which is the correct response to catching up
after a stall) and validating angles against the pan/tilt limits here (the controller's
job; this module stays independent).

The servo suite is 12 tests; the whole native suite is 36.

---

### Task 5: Shot state machine

**Files:**
- Create: `firmware/lib/dwarf/shooter.h`
- Create: `firmware/lib/dwarf/shooter.cpp`
- Test: `firmware/test/test_shooter/test_shooter.cpp`

The shooter owns one shot from request to cooldown. It never reads a clock and never touches hardware: callers pass `now` and the current servo angles, and read back `valveOpen()`.

- [ ] **Step 1: Write the failing test**

Create `firmware/test/test_shooter/test_shooter.cpp`:

```cpp
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd firmware && pio test -e native -f test_shooter`
Expected: `shooter.h: No such file or directory`.

- [ ] **Step 3: Write the header**

Create `firmware/lib/dwarf/shooter.h`:

```cpp
#pragma once
#include "types.h"

namespace dwarf {

enum class ShooterState { Idle, Move, Settle, Open, Cooldown };

struct ShooterConfig {
    uint16_t settleMs = 150;         // let the servos stop swinging before firing
    uint16_t maxBurstMs = 500;       // hard cap, independent of what the phone asks
    uint32_t cooldownMs = 5000;      // hard minimum gap between shots
    float settleToleranceDeg = 0.5f; // "arrived" window for both axes
};

class Shooter {
  public:
    explicit Shooter(ShooterConfig cfg = ShooterConfig{}) : cfg_(cfg) {}

    // Starts a shot. Returns false and sets *why to "busy", "cooldown" or "bad"
    // when the request cannot be accepted. The caller checks arm state, tank and
    // faults before calling.
    bool request(float pan, float tilt, uint16_t ms, Millis now, const char** why);

    // Advances the state machine. currentPan/currentTilt are the live servo angles.
    void update(Millis now, float currentPan, float currentTilt);

    // Closes the valve and returns to Idle. Used by safety paths.
    void abort();

    ShooterState state() const { return state_; }
    bool valveOpen() const { return valve_; }
    uint32_t shots() const { return shots_; }
    float targetPan() const { return targetPan_; }
    float targetTilt() const { return targetTilt_; }

  private:
    ShooterConfig cfg_;
    ShooterState state_ = ShooterState::Idle;
    bool valve_ = false;
    uint32_t shots_ = 0;
    float targetPan_ = 0.0f;
    float targetTilt_ = 0.0f;
    uint16_t burstMs_ = 0;
    Millis stamp_ = 0;
};

}  // namespace dwarf
```

- [ ] **Step 4: Write the implementation**

Create `firmware/lib/dwarf/shooter.cpp`:

```cpp
#include "shooter.h"

#include <cmath>

namespace dwarf {

bool Shooter::request(float pan, float tilt, uint16_t ms, Millis now, const char** why) {
    if (state_ != ShooterState::Idle) {
        if (why != nullptr) {
            *why = (state_ == ShooterState::Cooldown) ? "cooldown" : "busy";
        }
        return false;
    }
    if (ms == 0) {
        if (why != nullptr) *why = "bad";
        return false;
    }

    targetPan_ = pan;
    targetTilt_ = tilt;
    burstMs_ = (ms > cfg_.maxBurstMs) ? cfg_.maxBurstMs : ms;
    state_ = ShooterState::Move;
    stamp_ = now;
    return true;
}

void Shooter::update(Millis now, float currentPan, float currentTilt) {
    switch (state_) {
        case ShooterState::Move: {
            const bool arrived =
                std::fabs(currentPan - targetPan_) <= cfg_.settleToleranceDeg &&
                std::fabs(currentTilt - targetTilt_) <= cfg_.settleToleranceDeg;
            if (arrived) {
                state_ = ShooterState::Settle;
                stamp_ = now;
            }
            break;
        }
        case ShooterState::Settle:
            if (now - stamp_ >= cfg_.settleMs) {
                state_ = ShooterState::Open;
                stamp_ = now;
                valve_ = true;
            }
            break;
        case ShooterState::Open:
            if (now - stamp_ >= burstMs_) {
                valve_ = false;
                ++shots_;
                state_ = ShooterState::Cooldown;
                stamp_ = now;
            }
            break;
        case ShooterState::Cooldown:
            if (now - stamp_ >= cfg_.cooldownMs) state_ = ShooterState::Idle;
            break;
        case ShooterState::Idle:
            break;
    }
}

void Shooter::abort() {
    valve_ = false;
    state_ = ShooterState::Idle;
}

}  // namespace dwarf
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd firmware && pio test -e native -f test_shooter`
Expected: `5 Tests 0 Failures 0 Ignored` (13 after the addendum below).

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/dwarf/shooter.h firmware/lib/dwarf/shooter.cpp firmware/test/test_shooter/test_shooter.cpp
git commit -m "feat(firmware): add shot state machine with settle, burst cap and cooldown"
```

**Post-review addendum (applied in commit `33ca4cf`):** hostile-case analysis found three
problems. Two are fixed in this component; the third is handled in Task 10.

1. **`abort()` discarded a running cooldown**, so a disarm/re-arm or fault-clear cycle could
   fire two shots back to back and defeat the 5 s backstop. `abort` now takes `now` and is
   state-aware: `Move`/`Settle` return to `Idle` (nothing sprayed, so nothing to cool down);
   `Open` closes the valve, **counts the shot** and starts the cooldown from the abort
   moment; `Cooldown` closes the valve and leaves the original stamp untouched. The
   signature is `void abort(Millis now)`.
2. **The `Move` phase could wedge forever** — on a NaN angle, or a target the head cannot
   reach — leaving every later request rejected as "busy" until something called `abort()`,
   which nothing did. `ShooterConfig` gains `moveTimeoutMs = 2000`; a move that has not
   arrived by then abandons the shot with the valve closed and no shot counted. 2000 ms is
   generous: the widest reachable move is 120° of pan at 120°/s, which is one second.
3. **A stalled loop could leave the solenoid energised past the burst cap**, because a pure
   state machine enforces the cap only while `update()` keeps being called. This cannot be
   fixed here. Task 10 adds a one-shot hardware timer that closes the valve from an
   interrupt at 600 ms regardless of the loop, reports `VALVE_TIMEOUT` and disarms.

`test_abort_closes_the_valve_immediately` changed its expectation as part of item 1: it
aborts while the valve is open, which now yields `Cooldown` with the shot counted rather
than `Idle`. The shooter suite is 13 tests; the whole native suite is 49.

---

### Task 6: Controller — arm, aim, park, cfg

**Files:**
- Create: `firmware/lib/dwarf/controller.h`
- Create: `firmware/lib/dwarf/controller.cpp`
- Test: `firmware/test/test_controller/test_controller.cpp`

- [ ] **Step 1: Write the failing test**

Create `firmware/test/test_controller/test_controller.cpp`:

```cpp
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

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_arm_and_disarm);
    RUN_TEST(test_heartbeat_has_no_ack);
    RUN_TEST(test_unknown_command_is_acked_as_bad);
    RUN_TEST(test_aim_is_clamped_to_limits_and_slews);
    RUN_TEST(test_park_returns_to_zero);
    RUN_TEST(test_cfg_narrows_limits_and_pulls_target_in);
    RUN_TEST(test_cfg_with_inverted_range_is_rejected);
    return UNITY_END();
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd firmware && pio test -e native -f test_controller`
Expected: `controller.h: No such file or directory`.

- [ ] **Step 3: Write the header**

Create `firmware/lib/dwarf/controller.h`:

```cpp
#pragma once
#include "protocol.h"
#include "servo.h"
#include "shooter.h"
#include "types.h"

namespace dwarf {

struct ControllerConfig {
    Limits limits{};
    Millis heartbeatTimeoutMs = 3000;  // link considered dead after this silence
    float slewDegPerSec = 120.0f;
    Millis tankDebounceMs = 2000;      // a sloshing float switch must not trip a fault
    float fanOnC = 40.0f;
    float fanOffC = 35.0f;
    float overtempC = 60.0f;
    float overtempClearC = 55.0f;
    ShooterConfig shooter{};
};

struct Ack {
    bool present = false;
    const char* cmd = "";
    bool ok = false;
    const char* why = nullptr;
};

class Controller {
  public:
    explicit Controller(ControllerConfig cfg = ControllerConfig{})
        : cfg_(cfg), shooter_(cfg.shooter) {}

    // Applies one command and returns the acknowledgement to notify, if any.
    Ack handle(const Command& c, Millis now);

    // Advances time: tank debounce, faults, heartbeat, servo slew, shot machine.
    // tankSwitchClosed is true while the float switch reports water.
    void update(Millis now, bool tankSwitchClosed, float tempC);

    Status status() const;

    bool armed() const { return armed_; }
    bool valveOpen() const { return shooter_.valveOpen(); }
    bool pumpOn() const { return armed_ && tankOk_ && fault_ == Fault::None; }
    bool chargeOn() const { return charge_; }
    bool fanOn() const { return fan_; }
    float pan() const { return pan_; }
    float tilt() const { return tilt_; }
    Fault fault() const { return fault_; }
    ShooterState shooterState() const { return shooter_.state(); }

  private:
    void enterSafeState(Millis now);

    ControllerConfig cfg_;
    Shooter shooter_;
    bool armed_ = false;
    bool charge_ = true;   // fail-safe default: the phone must be able to boot
    bool fan_ = false;
    bool fanCmd_ = false;
    bool fanAuto_ = false;
    bool tankOk_ = true;
    bool tankLowPending_ = false;
    bool linkUp_ = false;
    Fault fault_ = Fault::None;
    float pan_ = 0.0f;
    float tilt_ = 0.0f;
    float targetPan_ = 0.0f;
    float targetTilt_ = 0.0f;
    float temp_ = 0.0f;
    Millis lastCmd_ = 0;
    Millis lastUpdate_ = 0;
    Millis tankLowSince_ = 0;
};

}  // namespace dwarf
```

- [ ] **Step 4: Write the implementation**

Create `firmware/lib/dwarf/controller.cpp`:

```cpp
#include "controller.h"

namespace dwarf {

Ack Controller::handle(const Command& c, Millis now) {
    Ack ack;
    if (c.type == CmdType::None) {
        ack.present = true;
        ack.cmd = "?";
        ack.ok = false;
        ack.why = "bad";
        return ack;
    }

    lastCmd_ = now;
    linkUp_ = true;

    switch (c.type) {
        case CmdType::Hb:
            break;

        case CmdType::Arm:
            ack.present = true;
            ack.cmd = "arm";
            if (c.flag && fault_ != Fault::None) {
                ack.ok = false;
                ack.why = "fault";
                break;
            }
            armed_ = c.flag;
            if (!armed_) shooter_.abort(now);
            ack.ok = true;
            break;

        case CmdType::Aim:
            targetPan_ = clampf(c.pan, cfg_.limits.panMin, cfg_.limits.panMax);
            targetTilt_ = clampf(c.tilt, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            break;

        case CmdType::Park:
            targetPan_ = 0.0f;
            targetTilt_ = 0.0f;
            ack.present = true;
            ack.cmd = "park";
            ack.ok = true;
            break;

        case CmdType::Shoot: {
            ack.present = true;
            ack.cmd = "shoot";
            ack.ok = false;
            if (!armed_) {
                ack.why = "disarmed";
                break;
            }
            // Tank first: an empty tank always raises Fault::TankEmpty, so
            // checking the fault first would make the "tank" code unreachable.
            if (!tankOk_) {
                ack.why = "tank";
                break;
            }
            if (fault_ != Fault::None) {
                ack.why = "fault";
                break;
            }
            const float p = clampf(c.pan, cfg_.limits.panMin, cfg_.limits.panMax);
            const float t = clampf(c.tilt, cfg_.limits.tiltMin, cfg_.limits.tiltMax);
            const char* why = nullptr;
            if (shooter_.request(p, t, c.ms, now, &why)) {
                targetPan_ = p;
                targetTilt_ = t;
                ack.ok = true;
            } else {
                ack.why = why;
            }
            break;
        }

        case CmdType::Charge:
            charge_ = c.flag;
            ack.present = true;
            ack.cmd = "charge";
            ack.ok = true;
            break;

        case CmdType::Fan:
            fanCmd_ = c.flag;
            ack.present = true;
            ack.cmd = "fan";
            ack.ok = true;
            break;

        case CmdType::Cfg:
            ack.present = true;
            ack.cmd = "cfg";
            if (c.panMin >= c.panMax || c.tiltMin >= c.tiltMax) {
                ack.ok = false;
                ack.why = "bad";
                break;
            }
            cfg_.limits = Limits{c.panMin, c.panMax, c.tiltMin, c.tiltMax};
            targetPan_ = clampf(targetPan_, c.panMin, c.panMax);
            targetTilt_ = clampf(targetTilt_, c.tiltMin, c.tiltMax);
            ack.ok = true;
            break;

        case CmdType::None:
            break;
    }

    return ack;
}

void Controller::update(Millis now, bool tankSwitchClosed, float tempC) {
    const Millis dt = now - lastUpdate_;
    lastUpdate_ = now;
    temp_ = tempC;

    if (!tankSwitchClosed) {
        if (!tankLowPending_) {
            tankLowPending_ = true;
            tankLowSince_ = now;
        } else if (now - tankLowSince_ >= cfg_.tankDebounceMs) {
            tankOk_ = false;
        }
    } else {
        tankLowPending_ = false;
        tankOk_ = true;
    }

    // Overtemp outranks tank level and disarms immediately.
    if (temp_ >= cfg_.overtempC) {
        fault_ = Fault::Overtemp;
        armed_ = false;
        shooter_.abort(now);
    } else if (fault_ == Fault::Overtemp && temp_ <= cfg_.overtempClearC) {
        fault_ = Fault::None;
    }
    if (fault_ != Fault::Overtemp) {
        fault_ = tankOk_ ? Fault::None : Fault::TankEmpty;
    }

    if (linkUp_ && now - lastCmd_ > cfg_.heartbeatTimeoutMs) {
        enterSafeState(now);
        linkUp_ = false;
    }

    pan_ = slewToward(pan_, targetPan_, cfg_.slewDegPerSec, dt);
    tilt_ = slewToward(tilt_, targetTilt_, cfg_.slewDegPerSec, dt);
    shooter_.update(now, pan_, tilt_);

    if (temp_ >= cfg_.fanOnC) fanAuto_ = true;
    if (temp_ <= cfg_.fanOffC) fanAuto_ = false;
    fan_ = fanCmd_ || fanAuto_;
}

void Controller::enterSafeState(Millis now) {
    armed_ = false;
    shooter_.abort(now);
    targetPan_ = 0.0f;
    targetTilt_ = 0.0f;
    charge_ = true;
}

Status Controller::status() const {
    Status s;
    s.armed = armed_;
    s.pan = pan_;
    s.tilt = tilt_;
    s.tankOk = tankOk_;
    s.pump = pumpOn();
    s.charge = charge_;
    s.fan = fan_;
    s.temp = temp_;
    s.fault = fault_;
    s.shots = shooter_.shots();
    return s;
}

}  // namespace dwarf
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd firmware && pio test -e native -f test_controller`
Expected: `7 Tests 0 Failures 0 Ignored`.

- [ ] **Step 6: Commit**

```bash
git add firmware/lib/dwarf/controller.h firmware/lib/dwarf/controller.cpp firmware/test/test_controller/test_controller.cpp
git commit -m "feat(firmware): add controller with arm, aim, park and limit config"
```

---

### Task 7: Controller — heartbeat safe state

**Files:**
- Modify: `firmware/test/test_controller/test_controller.cpp` (append tests and RUN_TEST lines)

The behaviour is already implemented in Task 6, so this task is a test-only task that pins it down. Run the tests first: if they pass immediately, that is the expected outcome here, and the value is the regression net.

- [ ] **Step 1: Write the tests**

Add above `main` in `firmware/test/test_controller/test_controller.cpp`:

```cpp
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

void test_link_loss_aborts_the_shot_cycle() {
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
    TEST_ASSERT_TRUE(c.shooterState() == ShooterState::Idle);  // abort() ran
}
```

Add to `main`:

```cpp
    RUN_TEST(test_link_loss_disarms_parks_and_restores_charging);
    RUN_TEST(test_heartbeats_keep_the_link_alive);
    RUN_TEST(test_link_loss_aborts_the_shot_cycle);
```

- [ ] **Step 2: Run the tests**

Run: `cd firmware && pio test -e native -f test_controller`
Expected: `10 Tests 0 Failures 0 Ignored`.

If `test_link_loss_aborts_the_shot_cycle` fails, check that `enterSafeState()` calls `shooter_.abort()` before the shooter's own `update()` runs in the same tick.

- [ ] **Step 3: Commit**

```bash
git add firmware/test/test_controller/test_controller.cpp
git commit -m "test(firmware): pin down heartbeat-loss safe state"
```

---

### Task 8: Controller — pump, tank, overtemp, fan

**Files:**
- Modify: `firmware/test/test_controller/test_controller.cpp` (append tests and RUN_TEST lines)

- [ ] **Step 1: Write the tests**

Add above `main`:

```cpp
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
```

Add to `main`:

```cpp
    RUN_TEST(test_pump_runs_only_while_armed_and_healthy);
    RUN_TEST(test_tank_low_is_debounced_then_faults_and_blocks_shots);
    RUN_TEST(test_overtemp_disarms_and_clears_with_hysteresis);
    RUN_TEST(test_fan_runs_on_command_or_heat);
    RUN_TEST(test_shoot_is_rejected_when_disarmed);
```

- [ ] **Step 2: Run the tests**

Run: `cd firmware && pio test -e native -f test_controller`
Expected: `15 Tests 0 Failures 0 Ignored`.

- [ ] **Step 3: Commit**

```bash
git add firmware/test/test_controller/test_controller.cpp
git commit -m "test(firmware): cover pump, tank debounce, overtemp and fan rules"
```

---

### Task 9: Controller — full shot sequence

**Files:**
- Modify: `firmware/test/test_controller/test_controller.cpp` (append test and RUN_TEST line)

This is the one test that exercises the whole library the way the phone will drive it.

- [ ] **Step 1: Write the test**

Add above `main`:

```cpp
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
```

Note the heartbeat loop at the end: `advance()` sends no commands, so without heartbeats the 3 s timeout would disarm the controller before the cooldown expires. That is the behaviour pinned down in Task 7, and it is exactly what the phone must do in the field.

Add to `main`:

```cpp
    RUN_TEST(test_arm_aim_shoot_cooldown_sequence);
```

- [ ] **Step 2: Run the whole native suite**

Run: `cd firmware && pio test -e native`
Expected: all four suites pass — `test_protocol`, `test_servo`, `test_shooter`, `test_controller` — ending in `SUMMARY: ... 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add firmware/test/test_controller/test_controller.cpp
git commit -m "test(firmware): cover the full arm-aim-shoot-cooldown sequence"
```

---

### Task 10: Hardware layer with a serial console

**Files:**
- Create: `firmware/src/pins.h`
- Create: `firmware/src/main.cpp`

This task brings up the real hardware without BLE. Commands arrive over the USB serial monitor instead, one JSON object per line, which stays in the firmware afterwards as the debugging path when BLE misbehaves.

- [ ] **Step 1: Write the pin map**

Create `firmware/src/pins.h`:

```cpp
#pragma once

// ESP32 DevKit v1 (board = esp32dev). Change these when using another board.
constexpr int PIN_SERVO_PAN = 18;
constexpr int PIN_SERVO_TILT = 19;
constexpr int PIN_VALVE = 25;    // MOSFET gate, solenoid valve
constexpr int PIN_PUMP = 26;     // MOSFET gate, pump power
constexpr int PIN_FAN = 27;      // MOSFET gate, 5 V fan
constexpr int PIN_CHARGER = 14;  // high-side switch enable, iPhone USB 5 V
constexpr int PIN_FLOAT = 34;    // input only: needs an external 10k pull-up to 3V3
constexpr int PIN_ONEWIRE = 4;   // DS18B20 data, 4.7k pull-up to 3V3

// Mechanical trim per servo, in microseconds. Both are set during the bench
// checklist so that a commanded 0 degrees points the head straight ahead.
constexpr float PAN_TRIM_US = 0.0f;
constexpr float TILT_TRIM_US = 0.0f;

// The float switch is wired to close to GND while there is water in the tank,
// so LOW means the tank is fine.
constexpr int FLOAT_WATER_PRESENT_LEVEL = LOW;
```

- [ ] **Step 2: Write main.cpp**

Create `firmware/src/main.cpp`:

```cpp
#include <Arduino.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>
#include <OneWire.h>
#include <esp_task_wdt.h>

#include <cstring>

#include "controller.h"
#include "pins.h"
#include "protocol.h"
#include "servo.h"

using namespace dwarf;

namespace {

Controller g_controller;
Servo g_panServo;
Servo g_tiltServo;
OneWire g_oneWire(PIN_ONEWIRE);
DallasTemperature g_tempSensor(&g_oneWire);

// Independent backstop for the burst cap. Shooter enforces the cap in software,
// but only while loop() keeps calling update(). If the loop ever blocks while
// the valve is open, the solenoid would stay energised until the task watchdog
// resets the board — seconds of water at a cat. This timer closes the valve
// from an interrupt, whatever the loop is doing.
hw_timer_t* g_valveTimer = nullptr;
volatile bool g_valveHardStop = false;
bool g_valveWasOpen = false;

constexpr uint32_t kValveHardStopMs = 600;  // Shooter's 500 ms cap plus margin

void IRAM_ATTR onValveTimeout() {
    // Register write rather than digitalWrite: this must be safe from an ISR.
    // Valid for GPIO 0-31, which PIN_VALVE is.
    GPIO.out_w1tc = (1u << PIN_VALVE);
    g_valveHardStop = true;
}

float g_tempC = 22.0f;
Millis g_lastSensorRead = 0;
Millis g_lastStatus = 0;
Status g_lastSent;
char g_line[192];
size_t g_lineLen = 0;

bool tankOk() { return digitalRead(PIN_FLOAT) == FLOAT_WATER_PRESENT_LEVEL; }

bool statusChanged(const Status& a, const Status& b) {
    return a.armed != b.armed || a.tankOk != b.tankOk || a.pump != b.pump ||
           a.charge != b.charge || a.fan != b.fan || a.fault != b.fault ||
           a.shots != b.shots;
}

// Sends one message out. Task 11 adds a BLE notify here. n is the length the
// formatter returned; 0 means it refused because the message did not fit, in
// which case there is nothing valid to send.
void emit(const char* json, size_t n) {
    if (n == 0) return;
    Serial.println(json);
}

void applyOutputs() {
    g_panServo.writeMicroseconds(angleToMicros(g_controller.pan(), PAN_TRIM_US));
    g_tiltServo.writeMicroseconds(angleToMicros(g_controller.tilt(), TILT_TRIM_US));
    const bool valve = g_controller.valveOpen();
    if (valve && !g_valveWasOpen) {
        timerWrite(g_valveTimer, 0);
        timerAlarmWrite(g_valveTimer, kValveHardStopMs * 1000ULL, false);
        timerAlarmEnable(g_valveTimer);
    } else if (!valve && g_valveWasOpen) {
        timerAlarmDisable(g_valveTimer);
    }
    g_valveWasOpen = valve;

    digitalWrite(PIN_VALVE, valve ? HIGH : LOW);
    digitalWrite(PIN_PUMP, g_controller.pumpOn() ? HIGH : LOW);
    digitalWrite(PIN_FAN, g_controller.fanOn() ? HIGH : LOW);
    digitalWrite(PIN_CHARGER, g_controller.chargeOn() ? HIGH : LOW);
}

void handleJson(const char* json, Millis now) {
    const Ack ack = g_controller.handle(parseCommand(json), now);
    if (!ack.present) return;
    char buf[128];
    const size_t n = formatAck(ack.cmd, ack.ok, ack.why, buf, sizeof(buf));
    emit(buf, n);
}

// Reads one JSON object per line from the USB serial monitor.
void pollSerial(Millis now) {
    while (Serial.available() > 0) {
        const char ch = static_cast<char>(Serial.read());
        if (ch == '\n' || ch == '\r') {
            if (g_lineLen > 0) {
                g_line[g_lineLen] = '\0';
                handleJson(g_line, now);
                g_lineLen = 0;
            }
        } else if (g_lineLen < sizeof(g_line) - 1) {
            g_line[g_lineLen++] = ch;
        }
    }
}

void readSensors(Millis now) {
    if (now - g_lastSensorRead < 5000) return;
    g_lastSensorRead = now;
    g_tempSensor.requestTemperatures();
    const float t = g_tempSensor.getTempCByIndex(0);
    if (t > -100.0f) g_tempC = t;  // -127 means no sensor on the bus
}

void publishStatus(Millis now) {
    const Status s = g_controller.status();
    if (now - g_lastStatus < 1000 && !statusChanged(s, g_lastSent)) return;
    g_lastStatus = now;
    g_lastSent = s;
    char buf[256];
    const size_t n = formatStatus(s, buf, sizeof(buf));
    emit(buf, n);
}

}  // namespace

void setup() {
    Serial.begin(115200);

    pinMode(PIN_VALVE, OUTPUT);
    digitalWrite(PIN_VALVE, LOW);
    pinMode(PIN_PUMP, OUTPUT);
    digitalWrite(PIN_PUMP, LOW);
    pinMode(PIN_FAN, OUTPUT);
    digitalWrite(PIN_FAN, LOW);
    pinMode(PIN_CHARGER, OUTPUT);
    digitalWrite(PIN_CHARGER, HIGH);  // charging on by default, so the phone can boot
    pinMode(PIN_FLOAT, INPUT);

    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    g_panServo.setPeriodHertz(50);
    g_tiltServo.setPeriodHertz(50);
    g_panServo.attach(PIN_SERVO_PAN, 500, 2500);
    g_tiltServo.attach(PIN_SERVO_TILT, 500, 2500);

    g_tempSensor.begin();

    // 80 MHz APB clock divided by 80 gives a 1 MHz tick, so the alarm value is
    // microseconds. Counting up, no auto-reload: one shot per burst.
    g_valveTimer = timerBegin(0, 80, true);
    timerAttachInterrupt(g_valveTimer, &onValveTimeout, true);

    esp_task_wdt_init(5, true);
    esp_task_wdt_add(nullptr);

    g_controller.update(millis(), tankOk(), g_tempC);
    Serial.println("{\"boot\":\"dwarf\"}");
}

void loop() {
    const Millis now = millis();

    pollSerial(now);

    if (g_valveHardStop) {
        g_valveHardStop = false;
        g_valveWasOpen = false;
        static const char kValveTimeoutMsg[] = "{\"fault\":\"VALVE_TIMEOUT\"}";
        emit(kValveTimeoutMsg, sizeof(kValveTimeoutMsg) - 1);
        handleJson("{\"c\":\"arm\",\"v\":false}", now);  // disarm; needs a human
    }

    readSensors(now);
    g_controller.update(now, tankOk(), g_tempC);
    applyOutputs();
    publishStatus(now);

    esp_task_wdt_reset();
    delay(10);
}
```

- [ ] **Step 3: Compile for the board**

Run: `cd firmware && pio run -e esp32dev`
Expected: `SUCCESS`. If `esp_task_wdt_init` fails to compile with "too many arguments", the installed Arduino core is 3.x; pin the platform by changing `platform = espressif32@^6.9.0` to `platform = espressif32@6.9.0` and run `pio run -e esp32dev -t clean` first.

- [ ] **Step 4: Wire the bench rig**

No water yet. Build this on the bench:

| Signal | Connection |
|---|---|
| 12 V PSU | Buck 1 → 6 V for servos, buck 2 → 5 V for the ESP32 |
| Pan servo | Signal GPIO18, power 6 V, ground common with the ESP32 |
| Tilt servo | Signal GPIO19, power 6 V, ground common |
| Valve | 12 V through MOSFET on GPIO25, flyback diode across the coil |
| Pump | 12 V through MOSFET on GPIO26, flyback diode across the motor |
| Fan | 5 V through MOSFET on GPIO27 |
| Charger | LED plus resistor on GPIO14 for now, standing in for the load switch |
| Float switch | GPIO34 to switch to GND, plus a 10k pull-up from GPIO34 to 3V3 |
| DS18B20 | Data to GPIO4, 4.7k pull-up to 3V3, power 3V3 |

A single common ground for the 12 V supply, the servo rail and the ESP32 is required, otherwise servo pulses are not seen correctly.

- [ ] **Step 5: Flash and drive it over serial**

Run: `cd firmware && pio run -e esp32dev -t upload && pio device monitor`

Then type these lines into the monitor, one at a time:

```
{"c":"arm","v":true}
{"c":"aim","pan":30,"tilt":10}
{"c":"aim","pan":-30,"tilt":-10}
{"c":"shoot","pan":0,"tilt":0,"ms":300}
{"c":"arm","v":false}
```

Expected:
- each command echoes an ack, such as `{"ack":"arm","ok":true}`;
- status lines appear about once a second;
- the head servo turns smoothly between the two aim positions rather than snapping;
- on `shoot`, the valve MOSFET switches on for 300 ms about 150 ms after the servos stop (put a multimeter or an LED on the valve output to see it);
- with no commands for 3 seconds, a status line shows `"armed":false` and `"charge":true`.

- [ ] **Step 6: Set the servo trims**

With the head mechanically attached, command `{"c":"park"}` and check that the head points straight ahead. If it does not, adjust `PAN_TRIM_US` in `firmware/src/pins.h` by ±50 µs at a time (about 4.5°), re-flash, and repeat until it does. Do the same for the tilt axis with the nozzle horizontal.

- [ ] **Step 7: Commit**

```bash
git add firmware/src/pins.h firmware/src/main.cpp
git commit -m "feat(firmware): add hardware layer with serial command console"
```

---

### Task 11: BLE server

**Files:**
- Modify: `firmware/src/main.cpp`

Serial stays as it is. BLE is added next to it, and both feed the same `handleJson()`.

- [ ] **Step 1: Add BLE includes, UUIDs and globals**

In `firmware/src/main.cpp`, add below the existing includes:

```cpp
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
```

Inside the anonymous namespace, above `bool tankOk()`, add:

```cpp
// From the spec, section 7. These must match the iOS app exactly.
constexpr char kServiceUuid[] = "EC61AB6F-D20E-4217-93F9-4A3DF81B75D3";
constexpr char kCmdUuid[] = "7C7FBA40-4383-4738-AD6B-09986229ED6A";
constexpr char kStatusUuid[] = "6DF54A5A-41DC-4414-AB6A-1354C959CF0A";

struct CmdMsg {
    char json[192];
};

QueueHandle_t g_cmdQueue = nullptr;
NimBLECharacteristic* g_statusChar = nullptr;

// BLE writes arrive on the NimBLE task. Queue them and handle them in loop(),
// so all controller state stays on one task.
class CmdCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* ch) override {
        if (g_cmdQueue == nullptr) return;
        CmdMsg msg{};
        const std::string value = ch->getValue();
        size_t n = value.size();
        if (n > sizeof(msg.json) - 1) n = sizeof(msg.json) - 1;
        memcpy(msg.json, value.data(), n);
        msg.json[n] = '\0';
        xQueueSend(g_cmdQueue, &msg, 0);
    }
};

class ServerCallbacks : public NimBLEServerCallbacks {
    void onDisconnect(NimBLEServer* server) override {
        // Keep the gnome reachable after the phone walks away.
        NimBLEDevice::startAdvertising();
    }
};
```

- [ ] **Step 2: Notify over BLE as well as serial**

Replace the existing `emit` function with:

```cpp
void emit(const char* json, size_t n) {
    if (n == 0) return;  // formatter refused: message did not fit its buffer
    Serial.println(json);
    if (g_statusChar == nullptr) return;
    g_statusChar->setValue(reinterpret_cast<const uint8_t*>(json), n);
    g_statusChar->notify();
}
```

Note the length comes from the formatter's return value, never from `strlen`. On an
exact-fit serialisation ArduinoJson does not write a terminator, so `strlen` would read
past the buffer.

- [ ] **Step 3: Drain the BLE queue in the loop**

Add this function inside the anonymous namespace, below `pollSerial`:

```cpp
void pollBle(Millis now) {
    if (g_cmdQueue == nullptr) return;
    CmdMsg msg;
    while (xQueueReceive(g_cmdQueue, &msg, 0) == pdTRUE) {
        handleJson(msg.json, now);
    }
}
```

And call it in `loop()`, directly after `pollSerial(now);`:

```cpp
    pollBle(now);
```

- [ ] **Step 4: Start the BLE server in setup()**

In `setup()`, directly above `esp_task_wdt_init(5, true);`, add:

```cpp
    g_cmdQueue = xQueueCreate(8, sizeof(CmdMsg));

    NimBLEDevice::init("dwarf");
    NimBLEDevice::setMTU(185);
    NimBLEServer* server = NimBLEDevice::createServer();
    server->setCallbacks(new ServerCallbacks());

    NimBLEService* service = server->createService(kServiceUuid);
    NimBLECharacteristic* cmdChar =
        service->createCharacteristic(kCmdUuid, NIMBLE_PROPERTY::WRITE);
    cmdChar->setCallbacks(new CmdCallbacks());
    g_statusChar = service->createCharacteristic(
        kStatusUuid, NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ);
    service->start();

    NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
    advertising->addServiceUUID(kServiceUuid);
    advertising->start();
```

- [ ] **Step 5: Flash and test with nRF Connect**

Run: `cd firmware && pio run -e esp32dev -t upload && pio device monitor`

On your phone, install nRF Connect (Nordic Semiconductor) and:
1. Scan, then connect to the device named `dwarf`.
2. Open the service `EC61AB6F-…`.
3. On the `6DF54A5A-…` characteristic, tap the three-arrows icon to subscribe to notifications. Status lines should appear about once a second.
4. On the `7C7FBA40-…` characteristic, tap the up-arrow, choose the text format, and send `{"c":"arm","v":true}`.

Expected: an ack notification `{"ack":"arm","ok":true}` arrives, the next status shows `"armed":true`, and the pump output switches on.

5. Send `{"c":"shoot","pan":0,"tilt":0,"ms":300}` and watch the valve output pulse.
6. Close nRF Connect. Within 3 seconds the serial monitor must show a status with `"armed":false` and `"charge":true`.

- [ ] **Step 6: Commit**

```bash
git add firmware/src/main.cpp
git commit -m "feat(firmware): serve commands and status over BLE"
```

---

### Task 12: Wet bench rig and M1 sign-off

**Files:**
- Create: `hardware/bench-checklist.md`

Water is involved from here on. Work outdoors or over a tub, keep the 12 V supply and all connections off the wet surface, and use an RCD/GFCI-protected outlet.

- [ ] **Step 1: Write the checklist document**

Create `hardware/bench-checklist.md`:

```markdown
# Bench checklist (milestone M1)

Rig: 3 L tank, 12 V diaphragm pump (~4 bar, pressure switch), 12 V normally-closed
solenoid valve, 1–1.5 mm brass nozzle on the tilt servo, ESP32 bench wiring from
Task 10. Commands are sent from nRF Connect or the USB serial monitor.

| # | Check | How | Pass condition | Result |
|---|---|---|---|---|
| 1 | Valve is closed with no power | Power off, pressurise by hand-running the pump, then cut power | No drip from the nozzle | |
| 2 | Pump only runs when armed | Send `{"c":"arm","v":true}` then `{"c":"arm","v":false}` | Pump runs and stops with arm state | |
| 3 | Burst length | `{"c":"shoot","pan":0,"tilt":0,"ms":300}`, film at 60 fps or listen | Valve open for 0.3 s ±0.05 s | |
| 4 | Burst cap | `{"c":"shoot","pan":0,"tilt":0,"ms":5000}` | Valve closes after about 0.5 s | |
| 5 | Cooldown | Two shoot commands 1 s apart | Second is rejected with `"why":"cooldown"` | |
| 6 | Reach | Nozzle at gnome height (about 0.5 m), tilt swept for maximum distance, measure where the water lands | **≥ 6 m** | |
| 7 | Repeatability | Five shots at one tilt setting, mark each splash | All within about 0.5 m of each other | |
| 8 | Link loss | Disconnect nRF Connect mid-burst | Valve closes within 3 s, pump off, head parks, charger output on | |
| 9 | Tank empty | Lift the float switch for more than 2 s | Status shows `"tank":"low"` and `"fault":"TANK_EMPTY"`, pump off, shoot rejected with `"why":"fault"` | |
| 10 | Refill recovery | Drop the float switch back | Fault clears, arming works again | |
| 11 | Overtemp | Warm the DS18B20 in a hand or with a hairdryer above 60 °C | Disarms, `"fault":"OVERTEMP"`, fan output on | |
| 12 | Power cut | Pull the 12 V supply mid-burst | Valve shuts, nothing sprays | |
| 13 | Burst hard stop | Temporary test build: add `delay(3000)` immediately after the valve opens, so the loop stalls mid-burst | Valve closes at about 600 ms by interrupt, not after 3 s; `VALVE_TIMEOUT` is reported and the system disarms. Remove the delay afterwards | |

## Reach tuning

If check 6 fails:
1. Narrow the nozzle orifice (a smaller opening throws further at the same pressure).
2. Confirm the pump reaches its cut-out pressure: the motor should stop within a
   couple of seconds of the valve closing.
3. Check for air leaks on the suction side; a diaphragm pump that is drawing air
   loses most of its pressure.
4. Only then consider adding a 0.75 L accumulator.

## Servo trims

Final values measured in Task 10, step 6:
- `PAN_TRIM_US`:
- `TILT_TRIM_US`:
```

- [ ] **Step 2: Run the checklist**

Work through all 12 rows and fill in the Result column. Every row must pass before the firmware counts as done. Rows 1, 8 and 12 are the safety rows: if any of them fails, stop and fix the firmware or the wiring before running anything else.

- [ ] **Step 3: Run the full test suite one more time**

Run: `cd firmware && pio test -e native`
Expected: all four suites pass.

- [ ] **Step 4: Commit the filled-in checklist**

```bash
git add hardware/bench-checklist.md
git commit -m "docs(hardware): record M1 bench checklist results"
```

---

## Definition of done

- `pio test -e native` passes all four suites.
- `pio run -e esp32dev` compiles without warnings that touch `lib/dwarf`.
- Every row of `hardware/bench-checklist.md` passes, including a measured reach of 6 m or more.
- The BLE service, both characteristic UUIDs and every message shape match section 7 of the spec, and `protocol/fixtures/` holds the canonical messages the iOS side will test against.

## What this plan deliberately leaves out

- Anything iOS: that is the DwarfCore and DwarfApp plans.
- Pump current sensing, which the spec dropped because the float switch covers running dry.
- OTA updates. The gnome's head comes off, and the USB port is right there.
- Persisting `cfg` limits across reboots. The phone sends `cfg` on connect, which is one message on a link that has to work anyway.
