#pragma once
#include <cstddef>

#include "types.h"

namespace dwarf {

// Parses one JSON command object. A malformed message, an unknown command name
// or a missing required field all yield a Command whose type is CmdType::None.
Command parseCommand(const char* json);

// Serialises a status object into `out`, a buffer of `cap` bytes.
//
// On success, returns the number of bytes written (not counting the terminating
// NUL, i.e. always equal to strlen(out)) and leaves `out` NUL-terminated. This is
// the number of bytes actually written, not an snprintf-style "bytes that would
// have been needed" count. If the encoded message (including its NUL terminator)
// does not fit in `cap`, or `out` is null, or `cap` is 0, `out` is left as an empty,
// NUL-terminated string (when `cap` > 0) and 0 is returned; a truncated fragment is
// never returned.
//
// Non-finite float values (NaN, +/-infinity) in `s` serialise as JSON null.
size_t formatStatus(const Status& s, char* out, size_t cap);

// Serialises an acknowledgement into `out`, a buffer of `cap` bytes. `why` is
// written only when ok is false and `why` is non-null.
//
// Uses the same contract as formatStatus: on success, returns the number of bytes
// written (always equal to strlen(out)) and leaves `out` NUL-terminated; if the
// message does not fit, or `out` is null, or `cap` is 0, `out` is left as an empty,
// NUL-terminated string (when `cap` > 0) and 0 is returned.
size_t formatAck(const char* cmd, bool ok, const char* why, char* out, size_t cap);

// "TANK_EMPTY", "OVERTEMP", "VALVE_TIMEOUT", "TEMP_SENSOR", or "" for Fault::None.
const char* faultName(Fault f);

}  // namespace dwarf
