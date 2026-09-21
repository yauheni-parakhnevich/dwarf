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
    bool armed = false;
    float pan = 0.0f;
    float tilt = 0.0f;
    bool tankOk = true;
    bool pump = false;
    bool charge = true;
    bool fan = false;
    float temp = 0.0f;
    Fault fault = Fault::None;
    uint32_t shots = 0;
};

}  // namespace dwarf
