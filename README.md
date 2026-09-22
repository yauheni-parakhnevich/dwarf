# Dwarf

A garden gnome that squirts a little water at cats.

Cats use the vegetable beds. The usual deterrents either do nothing or are unpleasant —
ultrasonic emitters that everyone's ears eventually notice, or sprinklers that soak whatever
walks past, including people and the wrong animals. This is an attempt at something narrower:
recognise a cat, decide whether it should be discouraged, and give it a brief, gentle squirt
that lands where it can be shaken off in a second.

Nothing about it is meant to hurt or badly frighten an animal. That constraint is not a
disclaimer at the top of a README; it is most of the engineering below it.

## Where this actually is

| Part | State |
|---|---|
| `ios/DwarfCore` | **Done.** All the decision logic, 162 tests, no iOS frameworks |
| `firmware/lib/dwarf` | **Done.** Protocol, servos, shot state machine, safety watchdog, 92 tests |
| `firmware/src` | **Runs on real hardware.** Serial console; BLE is next |
| `ios/DwarfApp` | **Planned, not written.** Camera, CoreML, the radio, the web UI |
| The gnome itself | **Not built.** Parts not ordered, nothing printed |

So: the brain works and is heavily tested, the body exists on paper, and no cat has ever been
squirted.

## How it works

Three pieces, deliberately unequal.

**An old iPhone 6s** does all the thinking. It watches through the gnome's belly, runs motion
detection on a small grayscale frame, crops the interesting parts out of the 1080p image,
runs a YOLO model over them, tracks what it finds, and decides. A jailbroken 6s is a cheap,
sealed, well-supported computer with a good camera and a battery that survives a power cut.

**An ESP32** is a deliberately stupid actuator. It moves two servos, opens a valve, and
watches its own safety timers. It knows nothing about cats. If the phone stops talking to it
for three seconds it disarms itself, closes the valve and centres the head — so every
interesting failure ends with the water off.

**The gnome** is a printed shell about 55 cm tall. The head nods on a yoke; a hollow shaft
carries water and wiring up through the rotating neck, so nothing has to seal against a
turning joint. Everything that holds pressure is bought, never printed.

Between the phone and the ESP32 is a small JSON protocol over Bluetooth. Both sides' test
suites assert against the same message fixtures in `protocol/fixtures/`, so they cannot drift
apart quietly.

## The welfare rules

These live in one file, `FirePolicy.swift`, and they are the reason the project is shaped the
way it is.

- **Water only, about 300 ms of it.** Clamped into 200–400 ms in the policy and again at the
  wire, so no settings screen can widen it.
- **Never closer than 2 m,** because at close range the jet is a hard stream rather than a
  spray.
- **Three shots per animal,** budgeted by where it was standing and when, not by a tracker
  ID — so a cat that walks behind a bush and comes back does not get a fresh allowance.
- **Twenty shots an hour** for the whole system, whatever it thinks it is seeing.
- **Daylight only,** 07:00–20:00 and bright enough to see, because a soaking in the dark is a
  fright rather than a deterrent.
- **Only at a confirmed, still animal,** never one that is moving or tangled with another
  track. A moving target would be led, and this system deliberately cannot lead.
- **No-fire zones** the owner draws, and a minimum confidence before anything counts.

It runs in dry-run by default. Dry-run spends the same budgets and writes the same log as live
fire, because a dry run whose log does not predict live behaviour is worthless.

## Repository

```
ios/DwarfCore/      Swift package: every decision, no frameworks, 162 tests
ios/DwarfApp/       the iOS app — planned, not yet written
firmware/           PlatformIO project for the ESP32
protocol/fixtures/  wire-format examples both test suites assert against
hardware/           bill of materials, wiring, bench checklists
docs/               the design spec, the mechanical design, and the plans
tools/              fixture generation, model export, PDF rendering
```

`docs/superpowers/` is worth a look if you like reading how something was built rather than
just what it became. The plans carry a post-review addendum for every task, written after an
adversarial pass over the code that task produced — including the defects that pass found,
most of which came from the plan rather than the implementation.

## Building it

```bash
# the decision logic — 162 tests, well under a second
cd ios/DwarfCore && swift test

# the firmware's logic — 92 tests, no hardware needed
cd firmware && pio test -e native

# the firmware itself
cd firmware && pio run -e esp32dev
```

## A few things learned the hard way

Each of these was a real bug in this repository, found by a review pass rather than by a test.

- **A system can be entirely green and completely inert.** Detection answers a cycle or two
  late, so most cycles carry no news — but the tracker counted those silent cycles as looks
  that saw nothing, and with two hits needed out of the last three looks, a perfectly detected
  cat could never be confirmed. Every component passed its own tests. The assembled gnome
  would have tracked, aimed, and never fired.
- **A per-animal cap keyed by tracker ID is not a cap.** IDs churn whenever a cat walks behind
  a bush. Budgets are keyed by place and time now.
- **The second cat is the one you forget.** Ranking by confidence and acting only on the best
  track let a cat that had used its whole allowance keep the head pointed at itself, while
  another sat untreated a metre away.
- **`JSONSerialization` raises an uncatchable exception on NaN.** Swift's `catch` never runs;
  the process simply dies.
- **The Arduino ESP32 build script appends its own `-std=gnu++11`,** after yours, and GCC
  honours the last one. Ten tasks of green native tests hid it.
- **A floating MOSFET gate opens a valve.** Firmware cannot fix what happens before `setup()`
  runs; that one needs a resistor.

## Licence and credits

The code here is the author's. The detection model is
[Ultralytics YOLO11](https://github.com/ultralytics/ultralytics), which is **AGPL-3.0** —
weights are not committed to this repository, and `tools/export_model.py` downloads and
converts them locally.

Built with [Claude Code](https://claude.com/claude-code).
