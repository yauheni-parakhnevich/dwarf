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

enum class Fault { None, TankEmpty, Overtemp, ValveTimeout };

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
