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
            if (!std::isfinite(c.pan) || !std::isfinite(c.tilt)) return c;
            break;
        case CmdType::Shoot:
            if (!doc["pan"].is<float>() || !doc["tilt"].is<float>() ||
                !doc["ms"].is<uint16_t>()) {
                return c;
            }
            c.pan = doc["pan"].as<float>();
            c.tilt = doc["tilt"].as<float>();
            c.ms = doc["ms"].as<uint16_t>();
            if (!std::isfinite(c.pan) || !std::isfinite(c.tilt)) return c;
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
            if (!std::isfinite(c.panMin) || !std::isfinite(c.panMax) ||
                !std::isfinite(c.tiltMin) || !std::isfinite(c.tiltMax)) {
                return c;
            }
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
            return "";
    }
    return "";
}

}  // namespace dwarf
