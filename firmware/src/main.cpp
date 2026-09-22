#include <Arduino.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>
#include <NimBLEDevice.h>
#include <OneWire.h>
#include <esp_task_wdt.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

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
bool g_tempRequested = false;
Millis g_lastSensorRead = 0;
Millis g_lastStatus = 0;
Status g_lastSent;
char g_line[192];
size_t g_lineLen = 0;

// From the spec, section 7. These must match the iOS app exactly.
constexpr char kServiceUuid[] = "EC61AB6F-D20E-4217-93F9-4A3DF81B75D3";
constexpr char kCmdUuid[] = "7C7FBA40-4383-4738-AD6B-09986229ED6A";
constexpr char kStatusUuid[] = "6DF54A5A-41DC-4414-AB6A-1354C959CF0A";

struct CmdMsg {
    char json[192];
};

QueueHandle_t g_cmdQueue = nullptr;
NimBLECharacteristic* g_statusChar = nullptr;

// Which channel a command arrived on. Only used to decide whether the
// command may refresh the phone-liveness heartbeat -- see the big comment on
// g_bleConnected below and on Controller::handle() in controller.h. It never
// changes whether the command itself is executed: both channels stay real
// command paths.
enum class CmdSource { Serial, Ble };

// Liveness ownership. Serial and BLE both funnel into the same
// handle()/heartbeat, and Task 10's post-review addendum flagged that as the
// same shape as the self-feeding-watchdog bug an earlier review caught: two
// independent channels each capable of refreshing one 3 s liveness clock
// means a channel nobody is actually watching (a serial monitor left open on
// the bench) can keep "proving" the phone is alive after BLE -- the channel
// that actually matters -- has gone quiet. That would silently disable
// forceSafe()'s watchdog, which is the firmware's last line of defence.
//
// The fix: liveness belongs to at most one channel at a time.
//   - While a BLE central is connected AND has sent a real command recently
//     (see bleOwnsLiveness() below -- "recently" is the same 3 s window the
//     heartbeat itself uses), BLE alone owns the heartbeat. Serial commands
//     still execute (arm, aim, shoot, ... all still work -- the console
//     remains a real command path for debugging a misbehaving BLE link),
//     they just do not count as proof the phone is present.
//   - Otherwise -- no central connected, or one connected but silent for 3 s
//     or more (a "zombie" connection that never sent the radio-level
//     disconnect event, e.g. a crashed phone app) -- serial owns the
//     heartbeat, exactly as it did before BLE existed (Task 10's bench
//     workflow -- arm/park/shoot from the USB console with no phone anywhere
//     nearby -- keeps working unchanged).
// Ownership is tracked by CURRENT, RECENT proof of life, not by "has a
// central ever connected since boot" and not merely by "is a central
// currently attached at the radio level". A permanent, one-way handover to
// BLE on first connection would mean that after any disconnect -- planned,
// or the phone crashing -- nobody could use the serial console (the tool
// this firmware provides for exactly that situation, per Task 10: "the
// debugging path when BLE misbehaves") without a full power cycle. Gating on
// raw connection state alone very nearly repeats the original bug: measured
// on hardware, a central that connects and then falls silent forever (never
// triggering onDisconnect) let a subsequent serial command run with no
// watchdog ever re-engaging afterwards, because BLE still "owned" the slot
// without feeding it and serial's refreshes stayed suppressed. Neither
// problem needs a full power cycle or a permanent handover to fix: the
// instant a real disconnect is detected, onDisconnect below drives the
// controller to forceSafe() directly (so by the time ownership reverts to
// serial the gnome is already parked, disarmed and charging -- there is no
// stale liveness left for a bench session to mask), and the instant BLE's
// own proof of life goes stale -- disconnected or not -- ownership reverts
// to serial on its own.
volatile bool g_bleConnected = false;

// A raw "is a central attached" flag is not enough on its own: a central can
// connect and then go silent forever without ever sending the radio-level
// disconnect ServerCallbacks::onDisconnect reacts to -- a crashed phone app,
// one that lost its own network/foreground state but left the BLE link up,
// or simply a slow phone that has not sent its first message yet. If
// g_bleConnected alone gated serial's heartbeat refresh, that first ordinary
// 3 s timeout would still fire and disarm correctly (linkUp_ has its own
// clock, independent of any of this), but from that moment on NOTHING would
// be enforcing liveness at all: BLE still "owns" the slot but is not feeding
// it, and serial's refreshes stay suppressed because g_bleConnected is still
// true. Measured on hardware: a BLE central that connects and never sends a
// command lets a subsequent serial arm/command run with no watchdog ever
// re-engaging, for as long as the zombie connection lasts.
//
// The fix is to require BLE to have proven life RECENTLY, not merely to be
// connected: g_bleCmdSeen/g_lastBleCmd track whether a real command has
// arrived over BLE, and bleOwnsLiveness() below only credits BLE with
// ownership while that proof is still fresh (the same 3 s window
// Controller's own heartbeat uses). The instant BLE goes stale -- connected
// or not -- ownership reverts to serial automatically, without waiting for a
// radio-level disconnect event.
//
// Both are written from two tasks -- loop() (a real BLE command arriving)
// and the NimBLE host task (onConnect's reset) -- with no lock between them,
// same as g_bleConnected/g_bleJustDisconnected above/below, so both are
// volatile for the same reason: this is a plain-bool handoff, not a
// synchronised one, and volatile only keeps the compiler from caching a
// stale value in a register across that handoff. The worst a lost or
// reordered update here can do is misjudge ownership for one ~10 ms loop()
// tick, never corrupt Controller state itself (nothing here touches it
// directly).
volatile bool g_bleCmdSeen = false;
volatile Millis g_lastBleCmd = 0;

// Mirrors ControllerConfig::heartbeatTimeoutMs (default-constructed on
// g_controller below), which main.cpp has no getter for. Keep in sync with
// controller.h if that default ever changes.
constexpr Millis kBleOwnershipTimeoutMs = 3000;

bool bleOwnsLiveness(Millis now) {
    return g_bleConnected && g_bleCmdSeen && (now - g_lastBleCmd) < kBleOwnershipTimeoutMs;
}

// Set from the NimBLE host task's onDisconnect callback, consumed once from
// loop(). Controller is single-task-owned (see the comment on CmdCallbacks
// below): forceSafe() touches several of its fields without any locking, so
// it may only ever be called from the same task that calls update() and the
// rest of the controller API, i.e. loop(). This mirrors g_valveHardStop's
// ISR-to-loop() handoff exactly, for the same reason -- the BLE host task is
// just as much "somewhere else" as an interrupt is.
volatile bool g_bleJustDisconnected = false;

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
    void onConnect(NimBLEServer* server) override {
        (void)server;
        g_bleConnected = true;
        // A fresh connection has not proven anything yet: it must not be
        // credited with the previous connection's (or nobody's) recency.
        // Serial keeps liveness ownership until this central actually sends
        // its first command.
        g_bleCmdSeen = false;
    }

    void onDisconnect(NimBLEServer* server) override {
        (void)server;
        g_bleConnected = false;
        g_bleCmdSeen = false;
        g_bleJustDisconnected = true;
        // Keep the gnome reachable after the phone walks away.
        NimBLEDevice::startAdvertising();
    }
};

bool tankOk() { return digitalRead(PIN_FLOAT) == FLOAT_WATER_PRESENT_LEVEL; }

bool statusChanged(const Status& a, const Status& b) {
    return a.armed != b.armed || a.tankOk != b.tankOk || a.pump != b.pump ||
           a.charge != b.charge || a.fan != b.fan || a.fault != b.fault ||
           a.shots != b.shots;
}

// Sends one message out over both channels. n is the length the formatter
// returned; 0 means it refused because the message did not fit, in which
// case there is nothing valid to send. The length comes from the formatter's
// return value, never from strlen: on an exact-fit serialisation ArduinoJson
// does not write a terminator, so strlen would read past the buffer.
void emit(const char* json, size_t n) {
    if (n == 0) return;
    Serial.println(json);
    if (g_statusChar == nullptr) return;
    g_statusChar->setValue(reinterpret_cast<const uint8_t*>(json), n);
    g_statusChar->notify();
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

void handleJson(const char* json, Millis now, CmdSource source) {
    const Command cmd = parseCommand(json);

    // Record BLE's own proof of life using exactly the criterion Controller
    // uses for its heartbeat (a recognised command, not just any byte on the
    // wire): see bleOwnsLiveness() and the comment on g_bleCmdSeen above.
    if (source == CmdSource::Ble && cmd.type != CmdType::None) {
        g_bleCmdSeen = true;
        g_lastBleCmd = now;
    }

    // BLE always counts as proof of life for its own commands; serial counts
    // only while BLE does not currently own that role. This never gates
    // whether the command is executed -- ack/appearance is identical either
    // way -- only whether it feeds the 3 s heartbeat.
    const bool refreshHeartbeat = (source == CmdSource::Ble) || !bleOwnsLiveness(now);
    const Ack ack = g_controller.handle(cmd, now, refreshHeartbeat);
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
                handleJson(g_line, now, CmdSource::Serial);
                g_lineLen = 0;
            }
        } else if (g_lineLen < sizeof(g_line) - 1) {
            g_line[g_lineLen++] = ch;
        }
    }
}

// Drains commands queued by CmdCallbacks::onWrite (running on the NimBLE
// task) and handles them here on loop()'s task, same as pollSerial.
void pollBle(Millis now) {
    if (g_cmdQueue == nullptr) return;
    CmdMsg msg;
    while (xQueueReceive(g_cmdQueue, &msg, 0) == pdTRUE) {
        handleJson(msg.json, now, CmdSource::Ble);
    }
}

void readSensors(Millis now) {
    if (now - g_lastSensorRead < 5000) return;
    g_lastSensorRead = now;

    // Read what the previous request produced, then start the next one. A DS18B20 takes
    // up to 750 ms to convert at 12-bit resolution, and waiting for it here would stall
    // loop() for that long every five seconds. If such a stall lands inside an open
    // burst, the software-timed valve close misses the 600 ms hardware backstop, the ISR
    // force-closes the valve, and an ordinary shot is reported as a VALVE_TIMEOUT fault
    // that disarms the gnome. The interval is far longer than any conversion, so the
    // reading collected here is always the finished one.
    if (g_tempRequested) {
        // Straight through, sentinel and all. DallasTemperature reports -127 for a probe
        // that is not on the bus, and Controller::update is what turns that into
        // Fault::TempSensor and a disarm. Filtering it out here would feed the controller
        // the last plausible reading forever and silently remove thermal protection,
        // which is the exact hole isValidTempReading() was added to close.
        g_tempC = g_tempSensor.getTempCByIndex(0);
    }
    g_tempSensor.requestTemperatures();
    g_tempRequested = true;
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
    // Do not block loop() for the conversion; see readSensors().
    g_tempSensor.setWaitForConversion(false);

    // 80 MHz APB clock divided by 80 gives a 1 MHz tick, so the alarm value is
    // microseconds. Counting up, no auto-reload: one shot per burst.
    g_valveTimer = timerBegin(0, 80, true);
    timerAttachInterrupt(g_valveTimer, &onValveTimeout, true);

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

    esp_task_wdt_init(5, true);
    esp_task_wdt_add(nullptr);

    g_controller.update(millis(), tankOk(), g_tempC);
    Serial.println("{\"boot\":\"dwarf\"}");
}

void loop() {
    const Millis now = millis();

    pollSerial(now);
    pollBle(now);

    if (g_valveHardStop) {
        g_valveHardStop = false;
        g_valveWasOpen = false;
        // Tell the library the valve was closed behind its back: it aborts the
        // shot, counts it, starts the cooldown, disarms and latches
        // VALVE_TIMEOUT until the phone explicitly disarms. Never synthesise a
        // command here: handle() treats any command as proof the phone is
        // alive, so a synthesised disarm would starve the heartbeat safety net.
        g_controller.notifyValveForceClosed(now);
    }

    if (g_bleJustDisconnected) {
        g_bleJustDisconnected = false;
        // A known disconnect is handled at once rather than waiting out the
        // full 3 s heartbeat timeout -- see forceSafe()'s own doc comment,
        // which was written for exactly this call site. Deliberately
        // forceSafe(), never a synthesised {"c":"arm","v":false} through
        // handle(): that would touch lastCmd_/linkUp_ and could starve the
        // very heartbeat this is meant to react to.
        g_controller.forceSafe(now);
    }

    readSensors(now);
    g_controller.update(now, tankOk(), g_tempC);
    applyOutputs();
    publishStatus(now);

    esp_task_wdt_reset();
    delay(10);
}
