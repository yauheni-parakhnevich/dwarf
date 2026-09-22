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
