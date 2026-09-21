# DwarfCore

Every decision the gnome makes, as a plain Swift package: motion, tracking, aiming, and
whether to ask for water. No iOS frameworks, no camera, no Bluetooth, no clock of its own —
time is always a parameter, so the whole thing runs in a test in microseconds.

```
GrayFrame ─▶ MotionDetector ─▶ Scheduler ──▶ CropRequest  (what to look at next)
                                                  │
                                            (the app runs the model)
                                                  ▼
            DetectorReport ─▶ Tracker ─▶ Aimer ─▶ FirePolicy ─▶ FireDecision
```

`Cycle` owns all of it. Call `process(frame:detector:status:now:uptime:)` once per camera
frame and act on the `CycleOutput`.

## The contract this package cannot enforce

The package is pure logic, so several things it depends on can only be guaranteed by the app
around it. Each of these can be violated with no test in here failing. Ordered by what it
costs in the garden.

**Only send water through a decision.** `FireDecision.shoot` is the only authorised route to
the nozzle. Every welfare rule — the 2 m minimum range, the no-fire zones, three shots per
animal, twenty an hour, daylight only, confirmed and still — lives in `FirePolicy` and
nowhere else. The firmware knows about armed, tank, fault and its own cooldown; it does not
know how far away the cat is or whether it has already been sprayed twice. `Command.shoot` is
constructible directly because calibration is impossible otherwise, and the burst-length
ceiling is enforced there as a second line of defence, but range and zones are not and cannot
be. A test-fire button that skips the policy is a full-pressure jet with no minimum range.

**Map the decision honestly.** `.wouldShoot` is a dry run. Nothing stops an app from sending
a real `Command.shoot` for one, and a dry run that fires is worse than no dry run at all.

**Filter the model's classes.** Everything reaching `Detection` is treated as a cat.

**Say `.pending` when the detector has not answered.** `DetectorReport.answer([], capturedAt:)`
means the detector looked and saw nothing, which counts against confirmation. `.pending` means
no news. Passing an empty answer on every cycle the model is still busy starves confirmation
and the gnome never fires — see the Task 11 addendum in the plan for the demonstration.

**Timestamp detections with when the frame was captured**, not when the answer came back.
Stillness gates firing, and a late answer at the current time makes a moving animal look
stiller than it is. Constant latency cancels out; jitter does not.

**Keep `uptime` monotonic** and never derive it from the wall clock. `now` is the wall clock
and is used for one thing only: the active-hours window. Everything else — cooldowns, caps,
stillness, parking — is measured on `uptime`.

**Pass `nil` for `status` the moment the link's health is in doubt.** `DeviceStatus` carries
no timestamp and `FirePolicy` has no notion of how old it is. A cached "last known good"
status keeps authorising shots. The firmware's own 3 s heartbeat watchdog means those shots
are refused rather than fired, so this is a bookkeeping failure rather than a safety one —
the shot still counts against the animal's budget here while no water reaches it.

**Keep `SchedulerConfig.frameWidthPixels`/`frameHeightPixels` equal to the real capture
resolution**, and give the small `GrayFrame` the same field of view as the full-resolution
frame the model runs on. Blob rectangles are normalised against the small frame and used to
cut crops from the big one. Nothing here can check that the two agree, and when they do not,
the crops land beside the cat.

**Call `Cycle.update(calibration:)` whenever the calibration changes**, rather than only
persisting the new JSON.

**Look at `Aimer.residuals()` and `MaskSet.validate()`.** Both are computed here and acted on
nowhere. A calibration that fits badly at the near edge is exactly how a cat closer than 2 m
gets a fitted range just over 2 m.

**Call `process` at a rate the configs were tuned for.** `MotionConfig.alpha` is per frame,
and the tracker's windows are counted in detector answers.

## Running the tests

```bash
cd ios/DwarfCore && swift test
```

162 tests, well under a second. `Tests/DwarfCoreTests/FixtureTests.swift` reads
`protocol/fixtures/*.json`, the same files the firmware's C++ tests assert against, so the
two sides cannot drift apart silently.
