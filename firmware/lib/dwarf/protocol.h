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
