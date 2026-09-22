#include <Arduino.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>
#include <NimBLEDevice.h>
#include <OneWire.h>
#include <Preferences.h>
#include <esp_random.h>
#include <cmath>
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

// Not a plausible room temperature: nothing has been measured yet, and saying
// 22 would be inventing a reading. isValidTempReading() rejects NaN, so the
// controller raises TEMP_SENSOR and refuses to arm until a real conversion
// lands -- about ten seconds after boot, since the first pass only starts the
// conversion and the next one collects it. Booting with a comfortable default
// meant a ten-second window on every power-up where the gnome would arm with
// no thermal protection at all, reporting a number it had never taken.
float g_tempC = NAN;
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

// --- BLE access control --------------------------------------------------
//
// Originally the service was wide open: anyone in range could connect with
// nRF Connect and write cmd. The firmware's own limits bound the *damage* a
// write can do (angles clamped, bursts capped at 500 ms, 5 s cooldown, the
// hardware valve timer closing the solenoid from an ISR regardless of any
// of this), but none of that stops a stranger choosing to aim a burst at a
// person, or emptying the tank out of spite. This section closes that. It
// is a radio/transport policy, not decision logic, so -- per the
// lib/dwarf constraint -- it lives here and nowhere near Controller.
//
// Design:
//   - Bonding + LE Secure Connections + a passkey (mitm=true) are required
//     for `cmd`: WRITE_ENC | WRITE_AUTHEN on top of WRITE means the NimBLE
//     host itself rejects a write from an unencrypted or unauthenticated
//     link with a GATT error -- CmdCallbacks::onWrite is never entered for
//     that case, so our code cannot get this wrong because it never runs.
//     `status` gets the matching READ_ENC | READ_AUTHEN: an unbonded
//     central cannot even observe tank/fault/shots, because
//     NimBLECharacteristic::notify() silently skips any subscriber whose
//     link is not encrypted (see its `reqSec` check).
//   - The ESP32 has no display or keypad, so BLE_HS_IO_DISPLAY_ONLY plus a
//     passkey is the closest fit available: the gnome "shows" a code it
//     cannot actually display, and whoever pairs a new central must already
//     know it out of band. The passkey is NOT a compile-time constant --
//     this repository is public, and a passkey anyone can read in source is
//     not a passkey; it would give the appearance of MITM protection with
//     none of the substance. Each board draws its own random six-digit
//     passkey the first time it boots, persists it in NVS, and prints it
//     over serial on every boot (see loadOrCreatePasskey() below) -- so
//     learning it requires the same physical-USB-access trust boundary the
//     bond-erase escape hatch already sits behind, not a read of this file.
//   - Bonds persist in NVS across reboots: NimBLEDevice::init() below calls
//     nvs_flash_init() and ble_store_config_init() internally, and
//     CONFIG_BT_NIMBLE_MAX_BONDS is pinned to 1 in platformio.ini -- exactly
//     one phone is meant to hold a bond at a time; a second pairing requires
//     the serial escape hatch below first.
//   - Transmit power is set to the lowest level this radio supports
//     (ESP_PWR_LVL_N12, -12 dBm) in setup(). The phone lives centimetres
//     from this board inside the same gnome body, so ordinary BLE range is
//     never needed; cutting it shrinks who can even attempt to pair from
//     "anyone on the pavement" toward roughly arm's length. It is a range
//     reduction that raises the bar, not a hard boundary -- a directional
//     antenna extends any attacker's effective range regardless of our
//     transmit power, since receive sensitivity is what actually limits
//     them, not what we send at.
//
// Passkey generation and storage. Kept in NVS, next to the bonds it
// protects, under its own namespace so erasing it is a deliberate act (see
// eraseBleBonds() below) rather than a side effect of anything else that
// touches NVS.
constexpr const char* kPasskeyPrefsNamespace = "dwarf-ble";
constexpr const char* kPasskeyPrefsKey = "passkey";

// Six identical digits (10 values: 000000, 111111, ..., 999999) or six
// digits running consecutively in either direction (10 more: 012345 up
// through 456789, and 987654 down through 543210) are exactly the handful
// of guesses an attacker tries before anything else -- also, incidentally,
// 123456 is NimBLEServerCallbacks' documented "did you forget to set a
// passkey" sentinel (see NimBLEServer.cpp), so excluding it is doubly
// correct. Redrawing on a degenerate hit costs nothing at boot and removes
// all twenty of them from the guessable space for free.
bool isDegeneratePasskey(uint32_t v) {
    char digits[6];
    for (int i = 5; i >= 0; --i) {
        digits[i] = static_cast<char>(v % 10);
        v /= 10;
    }
    bool allSame = true;
    bool ascending = true;
    bool descending = true;
    for (int i = 1; i < 6; ++i) {
        if (digits[i] != digits[0]) allSame = false;
        if (digits[i] != digits[i - 1] + 1) ascending = false;
        if (digits[i] != digits[i - 1] - 1) descending = false;
    }
    return allSame || ascending || descending;
}

// esp_random() is the ESP32's hardware TRNG (not a seeded PRNG), so this is
// suitable for a security-relevant value. % 1000000 has a ~1e-7 relative
// bias (2^32 is not an exact multiple of 1e6), which matters nowhere near
// as much as the six-digit search space itself already does not: this is
// defence against a passer-by guessing or shoulder-surfing, not a
// cryptographic key, and needs to be typed by a human either way.
uint32_t drawPasskey() {
    uint32_t v;
    do {
        v = esp_random() % 1000000u;
    } while (isDegeneratePasskey(v));
    return v;
}

// Loads the passkey persisted from a previous boot, or draws and persists a
// fresh one if this is the first boot ever, or the most recent one after
// eraseBleBonds() ran (which deliberately clears this key too -- see its
// comment). Called once from setup(), and again from eraseBleBonds() itself.
uint32_t loadOrCreatePasskey() {
    Preferences prefs;
    prefs.begin(kPasskeyPrefsNamespace, /*readOnly=*/false);
    uint32_t pk;
    if (prefs.isKey(kPasskeyPrefsKey)) {
        pk = prefs.getUInt(kPasskeyPrefsKey, 0);
    } else {
        pk = drawPasskey();
        prefs.putUInt(kPasskeyPrefsKey, pk);
    }
    prefs.end();
    return pk;
}

// Set once in setup() from loadOrCreatePasskey(), and again by
// eraseBleBonds() when it draws a fresh one. Read by setup() to print it on
// every boot (see its own comment for why "every", not just the first).
uint32_t g_blePasskey = 0;

// While the pairing window is open the gnome answers to this instead of its own
// passkey. It is public on purpose, and publishing it costs nothing, because it
// only works during a window that can only be opened by pressing a button
// inside the body. The proof of physical access moves from "read the number off
// a serial console" to "you had the gnome open", which is the same claim made
// more cheaply -- and, unlike the serial route, it needs no computer in the
// garden.
constexpr uint32_t kOpenPairingPasskey = 0;
// Long enough to find the dialog and type six zeroes, short enough that a gnome
// left open does not stay pairable all afternoon.
constexpr Millis kPairingWindowMs = 60000;
// A press, not a knock. Servicing the gnome should not be able to wipe its bond
// by brushing against the deck.
constexpr Millis kPairingHoldMs = 3000;

Millis g_pairingWindowEnds = 0;
Millis g_pairButtonSince = 0;
bool g_pairButtonHandled = false;

bool pairingWindowOpen(Millis now) {
    return g_pairingWindowEnds != 0 && now < g_pairingWindowEnds;
}

// Serial-only escape hatch: erases every BLE bond and makes the gnome
// pairable again. Typed as a bare line, never JSON, so it can never be
// confused with a phone-originated command and never needs a parser.
//
// This is deliberately NOT part of the JSON wire protocol
// (firmware/lib/dwarf/protocol.h, protocol/fixtures/):
//   1. Its entire purpose is to recover from a broken BLE bond -- phone
//      restored, app reinstalled, NVS wiped on either side. In exactly that
//      situation BLE itself is the thing that no longer works, so a
//      wire-protocol command could never reach the firmware to run this in
//      the first place. It has to live on a channel that does not depend on
//      BLE already working, which only serial is.
//   2. It requires physical possession of the USB cable by construction.
//      Putting the same power on the wire protocol would mean a *bonded*
//      central could erase the legitimate phone's own bond over the air --
//      a foot-gun with no offsetting benefit, since a bonded phone has no
//      legitimate reason to ever do that remotely, and an unbonded central
//      cannot write cmd at all (that is this task's whole point).
//   3. Keeping it out of protocol.h keeps firmware/lib/dwarf/ exactly as
//      pure and Arduino/NimBLE-free as it already is, and leaves
//      protocol/fixtures/ and both the C++ and Swift test suites untouched.
constexpr const char* kEraseBondsLine = "erase-bonds";

struct CmdMsg {
    char json[192];
};

QueueHandle_t g_cmdQueue = nullptr;
NimBLECharacteristic* g_statusChar = nullptr;
NimBLEServer* g_server = nullptr;

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
// millis() at which the current link was established, or 0 when idle. Written
// from the NimBLE host task, read from loop(), hence volatile like its
// neighbours.
volatile Millis g_bleConnectedAt = 0;

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
        // When this link arrived, so a central that connects and then never
        // proves who it is can be shown the door. See dropUnauthenticated().
        g_bleConnectedAt = millis();
        // A fresh connection has not proven anything yet: it must not be
        // credited with the previous connection's (or nobody's) recency.
        // Serial keeps liveness ownership until this central actually sends
        // its first command.
        g_bleCmdSeen = false;
    }

    void onDisconnect(NimBLEServer* server) override {
        (void)server;
        g_bleConnected = false;
        g_bleConnectedAt = 0;
        g_bleCmdSeen = false;
        g_bleJustDisconnected = true;
        // Keep the gnome reachable after the phone walks away.
        NimBLEDevice::startAdvertising();
    }

    // Diagnostic only -- printed to serial, never onto the wire protocol
    // (this is not a Status or Ack and must not be confused with either).
    // Fires whenever pairing/bonding for a link completes, successfully or
    // not, which is the one moment worth surfacing on the bench: whether
    // the link that is about to start sending commands actually ended up
    // encrypted, authenticated (passkey verified) and bonded, or whether it
    // is limping along some lesser state a client library negotiated down
    // to. It changes nothing -- the WRITE_ENC | WRITE_AUTHEN flags on cmd
    // are what actually enforce this -- it just makes the outcome visible.
    void onAuthenticationComplete(ble_gap_conn_desc* desc) override {
        if (desc == nullptr) return;
        Serial.printf(
            "{\"bleAuth\":true,\"encrypted\":%s,\"authenticated\":%s,\"bonded\":%s}\n",
            desc->sec_state.encrypted ? "true" : "false",
            desc->sec_state.authenticated ? "true" : "false",
            desc->sec_state.bonded ? "true" : "false");
        // A bond is what the window was open for. Close it at once rather than
        // leaving the gnome pairable for the rest of the minute.
        if (desc->sec_state.bonded) g_pairingWindowEnds = 0;
    }
};

// Serial-only escape hatch for kEraseBondsLine (see its own comment above).
// Disconnects anyone currently attached (an already-encrypted link survives
// its own bond record being deleted -- the session keys already in RAM keep
// working until the link actually tears down -- so leaving a connected
// central alone here would let it keep commanding right up until it
// happened to disconnect on its own), erases every bond from NVS, draws and
// persists a fresh passkey, and makes sure advertising is running so a
// fresh pairing can start immediately.
//
// The passkey is redrawn here, not just the bonds: a gnome whose bonds were
// just wiped -- because it is about to be re-paired with a different phone,
// or because the old one is presumed lost -- must not go on answering to a
// number someone else once read off it. Applied to the running session at
// once (setSecurityPasskey) so the very next pairing attempt already uses
// it; no reboot needed, though the new value is also what a reboot would
// load from NVS from this point on.
//
// Deliberately touches none of Controller's state directly. The
// disconnect(s) issued here run the same ServerCallbacks::onDisconnect path
// as any other disconnect, which already sets g_bleJustDisconnected and
// therefore drives Controller::forceSafe() from loop() on the very next
// tick -- exactly Task 11's "a known disconnect is handled at once" design,
// reused rather than duplicated.
void eraseBleBonds() {
    const int before = NimBLEDevice::getNumBonds();
    if (g_server != nullptr) {
        for (uint16_t connId : g_server->getPeerDevices()) {
            g_server->disconnect(connId);
        }
    }
    NimBLEDevice::deleteAllBonds();
    NimBLEDevice::startAdvertising();  // idempotent if already advertising

    Preferences prefs;
    prefs.begin(kPasskeyPrefsNamespace, /*readOnly=*/false);
    g_blePasskey = drawPasskey();
    prefs.putUInt(kPasskeyPrefsKey, g_blePasskey);
    prefs.end();
    NimBLEDevice::setSecurityPasskey(g_blePasskey);

    Serial.printf("{\"erasedBonds\":true,\"before\":%d,\"after\":%d,\"blePasskey\":\"%06u\"}\n",
                  before, NimBLEDevice::getNumBonds(), g_blePasskey);
}

// Opens the window: forget the phone we knew, answer to the public passkey, and
// say so. Reuses eraseBleBonds() wholesale rather than repeating it, so the
// disconnect and the forceSafe() that follows behave exactly as they already do.
void openPairingWindow(Millis now) {
    eraseBleBonds();
    NimBLEDevice::setSecurityPasskey(kOpenPairingPasskey);
    g_pairingWindowEnds = now + kPairingWindowMs;
    Serial.printf("{\"pairingWindow\":\"open\",\"seconds\":%lu,\"passkey\":\"%06u\"}\n",
                  static_cast<unsigned long>(kPairingWindowMs / 1000), kOpenPairingPasskey);
}

void closePairingWindow() {
    g_pairingWindowEnds = 0;
    // Back to this gnome's own number, so the public one is good for exactly
    // the window it was opened for and not a second longer.
    NimBLEDevice::setSecurityPasskey(g_blePasskey);
    digitalWrite(PIN_STATUS_LED, LOW);
    Serial.println("{\"pairingWindow\":\"closed\"}");
}

// A hold, debounced by the hold itself: the button has to be down continuously
// for kPairingHoldMs before anything happens, and has to be released before it
// can fire again.
void pollPairingButton(Millis now) {
    const bool down = digitalRead(PIN_PAIR_BUTTON) == LOW;

    if (!down) {
        g_pairButtonSince = 0;
        g_pairButtonHandled = false;
        return;
    }
    if (g_pairButtonSince == 0) {
        g_pairButtonSince = now;
        return;
    }
    if (!g_pairButtonHandled && now - g_pairButtonSince >= kPairingHoldMs) {
        g_pairButtonHandled = true;
        openPairingWindow(now);
    }
}

// Blinks while the window is open, and shuts it when the minute is up.
void servicePairingWindow(Millis now) {
    if (g_pairingWindowEnds == 0) return;
    if (now >= g_pairingWindowEnds) {
        closePairingWindow();
        return;
    }
    digitalWrite(PIN_STATUS_LED, ((now / 250) % 2) == 0 ? HIGH : LOW);
}

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

// Reads one line per line from the USB serial monitor: either one JSON
// command object, or the bare kEraseBondsLine escape hatch (never both --
// see its comment above for why that command is deliberately not JSON).
void pollSerial(Millis now) {
    while (Serial.available() > 0) {
        const char ch = static_cast<char>(Serial.read());
        if (ch == '\n' || ch == '\r') {
            if (g_lineLen > 0) {
                g_line[g_lineLen] = '\0';
                if (std::strcmp(g_line, kEraseBondsLine) == 0) {
                    eraseBleBonds();
                } else {
                    handleJson(g_line, now, CmdSource::Serial);
                }
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
    // Inside the body, on the electronics deck: holding it for three seconds
    // forgets the paired phone and opens a minute to pair a new one. That is
    // the recovery path that needs no computer in the garden.
    pinMode(PIN_PAIR_BUTTON, INPUT_PULLUP);
    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

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

    // Lowest transmit power this radio supports, for both advertising and
    // any resulting connection: see the BLE access-control comment block
    // above for why range is not needed here and what this trades away.
    NimBLEDevice::setPower(ESP_PWR_LVL_N12, ESP_BLE_PWR_TYPE_ADV);
    NimBLEDevice::setPower(ESP_PWR_LVL_N12, ESP_BLE_PWR_TYPE_DEFAULT);

    // Bonding + LE Secure Connections + passkey entry (MITM). See the BLE
    // access-control comment block above for the full design and rationale.
    g_blePasskey = loadOrCreatePasskey();
    NimBLEDevice::setSecurityAuth(/*bonding=*/true, /*mitm=*/true, /*sc=*/true);
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
    NimBLEDevice::setSecurityPasskey(g_blePasskey);

    NimBLEServer* server = NimBLEDevice::createServer();
    server->setCallbacks(new ServerCallbacks());
    g_server = server;

    NimBLEService* service = server->createService(kServiceUuid);
    NimBLECharacteristic* cmdChar = service->createCharacteristic(
        kCmdUuid, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC |
                      NIMBLE_PROPERTY::WRITE_AUTHEN);
    cmdChar->setCallbacks(new CmdCallbacks());
    g_statusChar = service->createCharacteristic(
        kStatusUuid, NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ |
                          NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::READ_AUTHEN);
    service->start();

    NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
    advertising->addServiceUUID(kServiceUuid);
    advertising->start();

    esp_task_wdt_init(5, true);
    esp_task_wdt_add(nullptr);

    g_controller.update(millis(), tankOk(), g_tempC);
    Serial.println("{\"boot\":\"dwarf\"}");
    // Printed on every boot, not only the first: the owner will need this
    // again after replacing a phone or wiping the app, and a number the
    // gnome printed once, months ago, is not a recovery path. Reading it
    // needs a USB cable plugged into this console -- the same trust
    // boundary as the erase-bonds escape hatch that can redraw it.
    Serial.printf("{\"blePasskey\":\"%06u\"}\n", g_blePasskey);
}

// How long a central may stay connected without completing pairing.
//
// Connecting is not gated -- only reading and writing the protected
// characteristics is -- so without this a stranger can open links and simply
// hold them. NimBLE allows three at once, and nothing ever reclaims one, so a
// few idle connections lock the phone out of the gnome entirely: no commands,
// no heartbeat, and the firmware's own watchdog then disarms it. Denial of
// service rather than danger, but trivially achievable from the pavement and
// invisible from indoors.
//
// A minute, not the ten seconds this started at. Ten is ample for two machines
// to exchange a passkey and hopeless for a person, who has to notice the
// dialog, find the number and type it. The first attempt to pair a real phone
// was evicted twice mid-flow by this very guard, which is a poor way for a
// security measure to earn its keep: the board logged two connections fourteen
// seconds apart, both ending unencrypted. Sixty seconds barely helps an
// attacker, since squatting is only useful held indefinitely and they can
// reconnect either way. What matters is that the slot is always reclaimed.
constexpr Millis kAuthGraceMs = 60000;

// Disconnects a link that has been up past the grace period without becoming
// authenticated. Bonded reconnections re-encrypt in well under a second, so
// this never touches the phone.
void dropUnauthenticated(Millis now) {
    if (!g_bleConnected || g_bleConnectedAt == 0) return;
    if (now - g_bleConnectedAt < kAuthGraceMs) return;

    NimBLEServer* server = NimBLEDevice::getServer();
    if (server == nullptr) return;

    // Ask the stack, not our own bookkeeping: a link is authenticated only if
    // the Security Manager says so.
    for (uint16_t handle : server->getPeerDevices()) {
        ble_gap_conn_desc desc;
        if (ble_gap_conn_find(handle, &desc) != 0) continue;
        if (desc.sec_state.authenticated) {
            // Legitimate and paired: stop sweeping until the next connection.
            g_bleConnectedAt = 0;
            return;
        }
        server->disconnect(handle);
    }
}

void loop() {
    const Millis now = millis();

    pollSerial(now);
    pollBle(now);
    pollPairingButton(now);
    servicePairingWindow(now);
    dropUnauthenticated(now);

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
