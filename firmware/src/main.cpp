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
bool g_tempRequested = false;
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
        // Tell the library the valve was closed behind its back: it aborts the
        // shot, counts it, starts the cooldown, disarms and latches
        // VALVE_TIMEOUT until the phone explicitly disarms. Never synthesise a
        // command here: handle() treats any command as proof the phone is
        // alive, so a synthesised disarm would starve the heartbeat safety net.
        g_controller.notifyValveForceClosed(now);
    }

    readSensors(now);
    g_controller.update(now, tankOk(), g_tempC);
    applyOutputs();
    publishStatus(now);

    esp_task_wdt_reset();
    delay(10);
}
