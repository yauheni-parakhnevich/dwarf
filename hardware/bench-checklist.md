# Bench checklist (milestone M1)

Water is involved from here on. Work outdoors or over a tub, keep the 12 V supply and every
connection off the wet surface, and use an RCD-protected outlet.

**Rig:** 3 L tank, 12 V diaphragm pump (~4 bar, pressure switch), 12 V normally-closed
solenoid valve, 1–1.5 mm brass nozzle on the tilt servo, and the wiring in
[`wiring.md`](wiring.md) — including the four gate pull-downs and the two flyback diodes,
which are not optional and are not in the original bill of materials.

**Commands** go over the USB serial console (one JSON object per line) or over BLE from any
client that can write a characteristic. nRF Connect needs iOS 17; BLE Scanner works on
iOS 15, which is what this phone runs. The gnome advertises as `dwarf` on service
`EC61AB6F-D20E-4217-93F9-4A3DF81B75D3`; this board's BLE address is `54:43:B2:44:2F:9E`.

## Before any water

These come first because each one has already caught something real, and because a valve
that misbehaves dry will misbehave wet at four bar.

| # | Check | How | Pass condition | Result |
|---|---|---|---|---|
| 0a | No click at power-on | Everything wired, tank empty, power-cycle the ESP32 five times | The valve never clicks. A click means a gate pull-down is missing or on the wrong pin | |
| 0b | Dead probe refuses to arm | Unplug the DS18B20, then `{"c":"arm","v":true}` | `"temp":-127`, `"fault":"TEMP_SENSOR"`, arming refused | |
| 0c | Probe restored | Plug it back in | Fault clears within ~5 s, arming works | |
| 0d | Serial cannot mask a silent phone | Connect over BLE, send any command, then let BLE go quiet while flooding `{"c":"hb"}` over serial | The gnome goes safe about 3 s after BLE's last command. Serial must not keep it alive | |
| 0e | Disconnect is immediate | Arm, turn the fan on over BLE, then disconnect the central | Fan off in well under a second, not after 3 s | |
| 0f | The phone is bonded | Pair once from the phone, entering the passkey the gnome prints over serial, then disconnect and reconnect | The second connection asks for nothing and the board logs `"encrypted":true,"authenticated":true,"bonded":true` | **PASSED 2026-09-22** |
| 0g | The ground point is on the feet | Put a cat figurine in view and tap `mount` until the red dot sits at its feet, not its flank | The dot tracks the feet as the figurine moves | **Mechanism verified 2026-09-22** — a handheld phone needed 90°; a phone lying flat in the gnome should need 0°, so re-check it after mounting |

## With water

| # | Check | How | Pass condition | Result |
|---|---|---|---|---|
| 1 | Valve closed with no power | Power off, pressurise by hand-running the pump, then cut power | No drip from the nozzle | |
| 2 | Pump only runs when armed | `{"c":"arm","v":true}` then `{"c":"arm","v":false}` | Pump runs and stops with arm state | |
| 3 | Burst length | `{"c":"shoot","pan":0,"tilt":0,"ms":300}`, film at 60 fps or listen | Valve open for 0.3 s ±0.05 s | |
| 4 | Burst cap | `{"c":"shoot","pan":0,"tilt":0,"ms":5000}` | Valve closes after about 0.5 s | |
| 5 | Cooldown | Two shoot commands 1 s apart | Second rejected with `"why":"cooldown"` | |
| 6 | Reach | Nozzle at gnome height (~0.5 m), tilt swept for maximum distance, measure where the water lands | **≥ 6 m** | |
| 7 | Repeatability | Five shots at one tilt setting, mark each splash | All within about 0.5 m of each other | |
| 8 | Link loss | Disconnect nRF Connect mid-burst | Valve closes within 3 s, pump off, head parks, charger output on | |
| 9 | Tank empty | Lift the float switch for more than 2 s | `"tank":"low"`, `"fault":"TANK_EMPTY"`, pump off, shoot rejected | |
| 10 | Refill recovery | Drop the float switch back | Fault clears, arming works again | |
| 11 | Overtemp | Warm the DS18B20 in a hand or with a hairdryer above 60 °C | Disarms, `"fault":"OVERTEMP"`, fan output on | |
| 12 | Power cut | Pull the 12 V supply mid-burst | Valve shuts, nothing sprays | |
| 13 | Burst hard stop | Temporary build with `delay(3000)` immediately after the valve opens | Valve closes at about 600 ms by interrupt, not after 3 s; `VALVE_TIMEOUT` reported, system disarms. **Remove the delay afterwards** | |

Check 13 is the one worth doing properly. It is the only test of the hardware timer that
closes the valve when the software cannot, and it is the last thing standing between a
stalled loop and a tank emptied onto the lawn.

## Measure the jet, not just the reach

Check 6 asks where the water lands. Also note, at 2 m and at 6 m:

- Whether the jet is still a **spray** or has become a coherent stream. The 2 m minimum range
  exists because of this, and the number it is set to should be checked against what the
  nozzle actually produces rather than assumed.
- Roughly how wide the wetted patch is. A cat's head is about 10 cm; a patch much wider than
  that at 6 m means the calibration's aim precision is not the limiting factor.

## Reach tuning

If check 6 fails:

1. Narrow the nozzle orifice — a smaller opening throws further at the same pressure.
2. Confirm the pump reaches its cut-out pressure: the motor should stop within a couple of
   seconds of the valve closing.
3. Check for air leaks on the suction side. A diaphragm pump drawing air loses most of its
   pressure.
4. Only then consider a 0.75 L accumulator.

## Servo trims

Measured during the dry bring-up, and copied into `firmware/src/pins.h`:

- `PAN_TRIM_US`:
- `TILT_TRIM_US`:

## Sign-off

M1 is met when every row above passes, the reach is at least 6 m, and the servo trims are
recorded in `pins.h` and committed.

Date: ______   Reach measured: ______ m   Jet at 2 m: spray / stream
