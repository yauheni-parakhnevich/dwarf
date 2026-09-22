# DwarfApp Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An iPhone app that watches the garden, finds cats with a CoreML model, tracks them through `DwarfCore`, and drives the gnome over Bluetooth — running in dry-run on the bench by the last task.

**Architecture:** All the adapter logic lives in a second Swift package, `DwarfAdapters`, which builds and tests on macOS with `swift test` exactly like `DwarfCore` does. Every framework that only exists on a phone sits behind a protocol with a fake, so the logic that decides *when* to look, *what* to send and *whether the link is healthy* is tested without a device. The Xcode app target is a shell: a camera, a screen, and a run loop. What cannot be tested on a Mac — the model's speed, the radio, the water — is isolated into four tasks that say so in their titles.

**Tech Stack:** Swift 6.4 toolchain, SwiftPM, XCTest. iOS 15 deployment target. AVFoundation, CoreML, CoreBluetooth, Accelerate. XcodeGen for the project file. Python + Ultralytics for the model export.

---

## Context the implementer needs

### What already exists

`ios/DwarfCore/` is finished and merged: 162 tests, no iOS frameworks, no clock of its own. It is the whole decision-making system — motion, crop scheduling, tracking, calibrated aiming, and the fire policy. **Read `ios/DwarfCore/README.md` before writing any code.** Its section "The contract this package cannot enforce" is not background reading; it is the specification for most of this plan. Several tasks below exist only to honour one of its bullets, and say which.

`firmware/` is a PlatformIO project for the ESP32. `lib/dwarf/` is the pure logic with 92 native tests, and the Arduino layer is being built now (firmware plan tasks 10–12). The protocol both sides speak is in `docs/superpowers/specs/2026-09-18-dwarf-cat-deterrent-design.md` §7, and `protocol/fixtures/*.json` holds message examples that both test suites assert against.

### What this plan does not cover

The web UI, the event store and dataset capture, the calibration screen and the mask editor are a **second plan**, written after this one lands. This plan ends with a gnome that tracks cats and decides, logs those decisions to the console, and can be watched on the phone's own screen. It deliberately stops before anything that needs a browser.

That means calibration and masks are **loaded** here, not edited: both are `Codable` in `DwarfCore`, and this plan reads them from JSON files on disk. Until the second plan exists, the only way to get a calibration onto the phone is to write the file — which is fine, because the first calibration cannot be recorded until the gnome is physically built anyway.

### Facts verified on this machine, 2026-09-22

Do not re-derive these; they were checked, and two of them nearly ended the project.

- **Xcode 27.0**, iOS 27 SDK. Its `MinimumDeploymentTarget` is **15.0** — exactly the floor, and the iPhone 6s tops out at iOS 15.8. A probe targeting `arm64-apple-ios15.0` importing CoreBluetooth, AVFoundation, CoreML and Network compiles clean.
- **Swift 6.4** (`swiftlang-6.4.0.34.1`). `DwarfCore` uses swift-tools-version 5.9 and Swift 5 language mode; match that, do not opt this package into Swift 6 strict concurrency.
- **The ESP32 is an ESP32-D0WD-V3**, 4 MB flash, MAC `54:43:b2:44:2f:9c`. Its **BLE address is `54:43:b2:44:2f:9e`** — the chip derives the Bluetooth address from the base MAC plus two. That is how the app identifies this specific gnome.
- The USB bridge is a **CH9102** (`1A86:55D4`), bound by macOS without a driver install.
- Homebrew's PlatformIO 6.2.0 needed `intelhex` installed into `/opt/homebrew/Cellar/platformio/6.2.0/libexec/bin/python` before esptool would run at all.
- **XcodeGen is not installed.** Task 1 needs `brew install xcodegen`.
- **Python 3.14.7 is the system Python and is too new for coremltools.** Task 2 builds its own virtual environment on an older interpreter.

### The phone's orientation, and why the code takes it as a parameter

`DwarfCore` reads an animal's ground point as `box.bottomCenter`. That is only the ground if **down in the image is down in the world**. The iPhone's video buffer comes out 1920×1080 with the long axis along the phone's long dimension, so the mount decides whether a rotation is needed:

- **Landscape** (phone lying on its side): the 1920 axis is horizontal in the world. Widest coverage of the garden, and the buffer is already gravity-down — no per-frame rotation at all, which on an A9 at 10 fps is worth having. **This plan defaults to landscape.** It requires the torso's internal width to take a 138.3 mm phone lying flat, call it 145 mm clear.
- **Portrait**: narrower horizontal field, and every frame needs a 90° rotation before `DwarfCore` sees it.

The mechanical design fixes neither; it only says the sled "must only fit one way". So `FrameGeometry` in Task 3 takes the orientation as a parameter and both mounts work. Choose the mount when the torso is printed, set one enum case, and recalibrate — the calibration fit absorbs everything else.

### Working method

Same as the two plans before it. A fresh subagent implements one task verbatim, then runs an adversarial analysis with real measurements against what it just wrote. The coordinator rules on each finding, the implementer fixes what is accepted, and the outcome is recorded as a post-review addendum in this file. That pass found a genuine defect in nearly every substantial task of the previous two plans, and almost all of them originated in the plan text rather than the implementation — including two that would have left a finished, fully green system unable to fire at a cat at all.

### Conventions

- Time is always a parameter, never read inside a decision. Monotonic `uptime` for every interval; wall-clock `now` only for the active-hours window.
- Nothing in `DwarfAdapters` imports UIKit. `ProcessInfo.thermalState` is cross-platform; `UIDevice.batteryLevel` is not, so it sits behind a protocol.
- `DeviceStatus` has no public initialiser — it is only produced by `IncomingMessage.decode`. Tests that need one **decode a JSON string**, which has the happy side effect of exercising the real decoder.
- Commit after every task, with the trailer `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## File structure

```
ios/DwarfApp/
  project.yml                        XcodeGen input; the .xcodeproj is generated, not committed
  App/
    DwarfAppMain.swift               @main, app lifecycle, idle timer
    RootView.swift                   the on-device screen
    CameraSource.swift               AVCaptureSession; iOS-only, deliberately thin
    BatteryReader.swift              UIDevice behind DwarfAdapters' protocol
    Info.plist
  DwarfAdapters/
    Package.swift
    Sources/DwarfAdapters/
      Clock.swift                    monotonic uptime + wall clock, and the guard on both
      FrameGeometry.swift            orientation, crop rects, box mapping — pure arithmetic
      FrameConverter.swift           CVPixelBuffer → GrayFrame, and crop extraction
      Detector.swift                 the Detector protocol and its box decoding
      CoreMLDetector.swift           the real model behind that protocol
      Transport.swift                the byte-level link protocol and its fake
      ActuatorLink.swift             heartbeat, acks, status freshness, reconnect
      PowerManager.swift             battery hysteresis, thermal, darkness
      Store.swift                    mode, calibration, masks, settings on disk
      Runtime.swift                  owns Cycle; honours DwarfCore's contract
    Tests/DwarfAdaptersTests/
      (one file per source file above)
tools/
  export_model.py                    YOLO11n → CoreML
  requirements-model.txt
```

The `.xcodeproj` is generated by XcodeGen and **gitignored**. The project file is a merge-conflict machine and every line of it is derivable from `project.yml`.

---

## Task 0: The adapters package

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Package.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/PackageTests.swift`

The package that holds everything testable. It depends on `DwarfCore` by relative path.

- [ ] **Step 1: Write the manifest**

Create `ios/DwarfApp/DwarfAdapters/Package.swift`:

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DwarfAdapters",
    platforms: [.macOS(.v13), .iOS(.v15)],
    products: [
        .library(name: "DwarfAdapters", targets: ["DwarfAdapters"])
    ],
    dependencies: [
        .package(path: "../../DwarfCore")
    ],
    targets: [
        .target(name: "DwarfAdapters", dependencies: [
            .product(name: "DwarfCore", package: "DwarfCore")
        ]),
        .testTarget(name: "DwarfAdaptersTests", dependencies: ["DwarfAdapters"])
    ]
)
```

- [ ] **Step 2: Write the failing test**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/PackageTests.swift`:

```swift
import XCTest
import DwarfCore
@testable import DwarfAdapters

final class PackageTests: XCTestCase {
    func testDwarfCoreIsLinkedAndUsable() {
        // The whole point of this package is to feed DwarfCore. If the relative path in
        // Package.swift is wrong, this is where it is discovered, rather than three tasks
        // later inside a CoreML wrapper.
        let cycle = Cycle(calibration: .empty)
        let frame = GrayFrame(width: 4, height: 4, pixels: [UInt8](repeating: 10, count: 16))
        let output = cycle.process(frame: frame, detector: .pending, status: nil,
                                   now: Date(), uptime: 0)

        // Dark frame, no calibration, no detections: nothing to do, and nothing to park
        // from either, since the head has never moved.
        XCTAssertEqual(output.decision, .none)
        XCTAssertTrue(output.tracks.isEmpty)
    }
}
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: the build fails — there is no `Sources/DwarfAdapters` directory, so SwiftPM reports `Source files for target DwarfAdapters should be located under .../Sources/DwarfAdapters`.

- [ ] **Step 4: Create the source directory with its first real file**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/DwarfAdapters.swift`:

```swift
/// The iOS side of the gnome: everything that touches a camera, a radio, a battery or a
/// disk, wrapped so that the parts worth testing can be tested on a Mac.
///
/// `DwarfCore` decides what the gnome does. This package is the set of adapters that feed
/// it and carry out what it decides, plus `Runtime`, which is the only thing that knows
/// about all of them at once. Read `ios/DwarfCore/README.md` first: its list of what that
/// package cannot enforce is the specification for most of the types in here.
public enum DwarfAdapters {
    /// Bumped when something on the wire or on disk changes shape, so a phone running an
    /// old build against new files says so instead of misreading them.
    public static let formatVersion = 1
}
```

- [ ] **Step 5: Run the test**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 1 test, with 0 failures`.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp
git commit -m "feat(app): add the DwarfAdapters package"
```

---

## Task 1: The Xcode app shell

**Files:**
- Create: `ios/DwarfApp/project.yml`
- Create: `ios/DwarfApp/App/DwarfAppMain.swift`
- Create: `ios/DwarfApp/App/RootView.swift`
- Modify: `.gitignore`

An app that launches, shows one screen, and links the package. No camera yet. The point of this task is to prove the build chain reaches an iOS 15 binary on a machine whose SDK is iOS 27.

**Prerequisite:** `brew install xcodegen`. If it is not installed, stop and say so rather than hand-writing a `.xcodeproj`.

- [ ] **Step 1: Write the project definition**

Create `ios/DwarfApp/project.yml`:

```yaml
name: DwarfApp
options:
  bundleIdPrefix: garden.dwarf
  deploymentTarget:
    iOS: "15.0"
  createIntermediateGroups: true
  groupSortPosition: top

packages:
  DwarfAdapters:
    path: DwarfAdapters

targets:
  DwarfApp:
    type: application
    platform: iOS
    sources:
      - path: App
    dependencies:
      - package: DwarfAdapters
        product: DwarfAdapters
    settings:
      base:
        SWIFT_VERSION: "5.0"
        TARGETED_DEVICE_FAMILY: "1"
        PRODUCT_BUNDLE_IDENTIFIER: garden.dwarf.app
        CURRENT_PROJECT_VERSION: "1"
        MARKETING_VERSION: "1.0"
        # TrollStore installs an unsigned .tipa, so the build never needs a team.
        CODE_SIGNING_ALLOWED: "NO"
        CODE_SIGNING_REQUIRED: "NO"
    info:
      path: App/Info.plist
      properties:
        CFBundleDisplayName: Dwarf
        UILaunchScreen: {}
        UIRequiresFullScreen: true
        # The phone lies on its side in the gnome's belly; see the plan's note on
        # orientation. Locking this stops iOS rotating the UI when the gnome is carried.
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationLandscapeLeft
          - UIInterfaceOrientationLandscapeRight
        NSCameraUsageDescription: The gnome watches the garden for cats.
        NSBluetoothAlwaysUsageDescription: The gnome talks to its actuator over Bluetooth.
        UIBackgroundModes:
          - bluetooth-central
```

- [ ] **Step 2: Write the app entry point**

Create `ios/DwarfApp/App/DwarfAppMain.swift`:

```swift
import SwiftUI

@main
struct DwarfAppMain: App {
    init() {
        // The camera only runs in the foreground, and a gnome whose screen has locked is
        // a gnome that has stopped watching. Every other power decision is in
        // PowerManager; this one has to happen before anything else starts.
        UIApplication.shared.isIdleTimerDisabled = true
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
```

- [ ] **Step 3: Write the screen**

Create `ios/DwarfApp/App/RootView.swift`:

```swift
import SwiftUI
import DwarfAdapters

struct RootView: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("Dwarf")
                .font(.largeTitle.bold())
            Text("format version \(DwarfAdapters.formatVersion)")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .foregroundStyle(.white)
    }
}
```

- [ ] **Step 4: Ignore the generated project**

Append to `.gitignore`:

```
ios/DwarfApp/DwarfApp.xcodeproj/
```

- [ ] **Step 5: Generate and build**

Run:

```bash
cd ios/DwarfApp && xcodegen generate
xcodebuild -project DwarfApp.xcodeproj -scheme DwarfApp -sdk iphoneos -configuration Debug build CODE_SIGNING_ALLOWED=NO
```

Expected: `** BUILD SUCCEEDED **`. This compiles for a real arm64 device against the iOS 15 deployment target without any signing identity, which is exactly how the `.tipa` for TrollStore will be produced later.

If the build instead fails with a deployment-target error, stop and report it: it means the SDK's floor has moved and the whole approach to this phone needs rethinking.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp .gitignore
git commit -m "feat(app): add the Xcode app shell, generated by XcodeGen"
```

---

## Task 2: Export the detection model

**Files:**
- Create: `tools/requirements-model.txt`
- Create: `tools/export_model.py`
- Create: `ios/DwarfApp/App/Models/.gitignore`

The model is a build input, not source. This task produces `yolo11n.mlpackage` reproducibly and puts it where Xcode will compile it into the app.

`uv` is installed and `python3.11` exists at `/opt/homebrew/bin/python3.11`. Use them: the system Python is 3.14, which coremltools does not support.

- [ ] **Step 1: Pin the dependencies**

Create `tools/requirements-model.txt`:

```
ultralytics==8.3.40
coremltools==8.1
```

- [ ] **Step 2: Write the export script**

Create `tools/export_model.py`:

```python
#!/usr/bin/env python3
"""Export YOLO11n to CoreML for the gnome.

The weights are AGPL-3.0 (Ultralytics), which is fine for this private project.

Run this through a 3.11 virtual environment, not the system Python:

    uv venv --python /opt/homebrew/bin/python3.11 .venv-model
    uv pip install --python .venv-model/bin/python -r tools/requirements-model.txt
    .venv-model/bin/python tools/export_model.py
"""

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DESTINATION = REPO / "ios" / "DwarfApp" / "App" / "Models"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="yolo11n.pt",
                        help="downloaded on first run if absent")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="640 is the M0 target; 416 and 320 are the fallbacks if the "
                             "6s cannot sustain three inferences a second")
    parser.add_argument("--half", action="store_true",
                        help="FP16 weights. Smaller and usually faster on the A9's GPU, "
                             "which has no Neural Engine to fall back on. Try this first "
                             "if M0 misses its target before dropping imgsz")
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.weights)
    # nms=True embeds Apple's NonMaximumSuppression stage in the model, so the app gets
    # boxes rather than a raw prediction tensor it would have to sort out itself on the
    # phone's CPU.
    exported = model.export(format="coreml", imgsz=args.imgsz, nms=True, half=args.half)

    DESTINATION.mkdir(parents=True, exist_ok=True)
    target = DESTINATION / "yolo11n.mlpackage"
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(exported), str(target))

    print(f"wrote {target}")
    print("input size:", args.imgsz, "half:", args.half)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Keep the model out of git but keep its directory**

Create `ios/DwarfApp/App/Models/.gitignore`:

```
# The model is a build input, reproducible from tools/export_model.py. A 6 MB binary in
# git history that changes whenever the export is re-run is not worth the convenience.
*.mlpackage
*.mlmodel
*.mlmodelc
```

- [ ] **Step 4: Run the export**

```bash
cd /Users/Yauheni_Parakhnevich/Workspace/dwarf
uv venv --python /opt/homebrew/bin/python3.11 .venv-model
# uv venv does not install pip into the environment, so install through uv itself.
uv pip install --python .venv-model/bin/python -r tools/requirements-model.txt
.venv-model/bin/python tools/export_model.py
```

Expected: `wrote .../ios/DwarfApp/App/Models/yolo11n.mlpackage`.

- [ ] **Step 5: Record what the model actually promises**

Run:

```bash
.venv-model/bin/python -c "
import coremltools as ct
m = ct.models.MLModel('ios/DwarfApp/App/Models/yolo11n.mlpackage')
print(m.get_spec().description)
" | head -60
```

Write the input name, the two output names and their shapes into the commit message. Task 5 decodes exactly these, and guessing is how a whole afternoon disappears.

**Measured on 2026-09-22 with ultralytics 8.3.40 and coremltools 8.1**, so this step is a
check that a re-export still matches rather than a discovery:

```
INPUT  image                640 x 640 image
INPUT  iouThreshold         double
INPUT  confidenceThreshold  double
OUTPUT confidence           (N, 80)
OUTPUT coordinates          (N, 4)
```

Three inputs, not one, and none of them is marked optional. `coordinates` rows are
`[x_center, y_center, width, height]` normalised to the input square. Task 5 supplies all
three and selects the image input by type rather than by name order. **If a re-export
differs from this, stop and report it** rather than adapting Task 5 quietly.

- [ ] **Step 6: Commit**

```bash
git add tools/requirements-model.txt tools/export_model.py ios/DwarfApp/App/Models/.gitignore
git commit -m "feat(tools): export YOLO11n to CoreML for the gnome"
```

---

## Task 3: Frame geometry

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/FrameGeometry.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/FrameGeometryTests.swift`

Pure arithmetic, no frameworks, and the single place where a sign error turns into the gnome spraying a fence. Three jobs: decide which way is down, turn a `CropRequest` into a pixel rectangle, and turn a model's box back into frame coordinates.

This task implements two bullets of `DwarfCore`'s contract: keeping `SchedulerConfig`'s pixel dimensions equal to the real frame, and giving the small grayscale frame the same field of view as the full one.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/FrameGeometryTests.swift`:

```swift
import XCTest
import DwarfCore
@testable import DwarfAdapters

final class FrameGeometryTests: XCTestCase {
    private let buffer = PixelSize(width: 1920, height: 1080)

    func testALandscapeMountNeedsNoRotation() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        XCTAssertEqual(geometry.frame, PixelSize(width: 1920, height: 1080))
        XCTAssertEqual(geometry.bufferPoint(frameX: 100, frameY: 50), PixelPoint(x: 100, y: 50))
    }

    func testAQuarterTurnSwapsTheFrameDimensions() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 1)
        XCTAssertEqual(geometry.frame, PixelSize(width: 1080, height: 1920))
    }

    func testEveryRotationMapsCornersToCorners() {
        // The cheapest possible check that a rotation is a rotation and not a fold: the
        // four frame corners must land on the four buffer corners, once each.
        for turns in 0..<4 {
            let geometry = FrameGeometry(buffer: buffer, quarterTurns: turns)
            let w = geometry.frame.width - 1
            let h = geometry.frame.height - 1
            let mapped = Set([
                geometry.bufferPoint(frameX: 0, frameY: 0),
                geometry.bufferPoint(frameX: w, frameY: 0),
                geometry.bufferPoint(frameX: 0, frameY: h),
                geometry.bufferPoint(frameX: w, frameY: h)
            ])
            let corners: Set<PixelPoint> = [
                PixelPoint(x: 0, y: 0),
                PixelPoint(x: 1919, y: 0),
                PixelPoint(x: 0, y: 1079),
                PixelPoint(x: 1919, y: 1079)
            ]
            XCTAssertEqual(mapped, corners, "quarterTurns \(turns)")
        }
    }

    func testACropRequestBecomesAPixelRectangle() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let request = CropRequest(rect: Rect(x: 0.25, y: 0.5, width: 0.25, height: 0.25),
                                  kind: .motion)
        let rect = geometry.pixelRect(of: request.rect)

        XCTAssertEqual(rect.x, 480)
        XCTAssertEqual(rect.y, 540)
        XCTAssertEqual(rect.width, 480)
        XCTAssertEqual(rect.height, 270)
    }

    func testACropRectangleIsClampedIntoTheFrame() {
        // Scheduler clamps its own rects, but a mask editor or a settings file can hand
        // over something that starts inside the frame and runs off the edge. Extracting
        // pixels from outside the buffer is a crash, not a bad crop.
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let rect = geometry.pixelRect(of: Rect(x: 0.9, y: 0.9, width: 0.5, height: 0.5))

        XCTAssertEqual(rect.x + rect.width, 1920)
        XCTAssertEqual(rect.y + rect.height, 1080)
        XCTAssertGreaterThan(rect.width, 0)
    }

    func testANonFiniteCropRectangleIsRefused() {
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        XCTAssertNil(geometry.validPixelRect(of: Rect(x: .nan, y: 0, width: 0.1, height: 0.1)))
        XCTAssertNil(geometry.validPixelRect(of: Rect(x: 0, y: 0, width: 0, height: 0.1)))
    }

    func testALetterboxedBoxComesBackToWhereItStarted() {
        // The round trip that matters: a box drawn in frame coordinates, projected into
        // the model's padded square, and read back out must land where it began. Every
        // sign error in the letterbox arithmetic shows up here.
        let geometry = FrameGeometry(buffer: buffer, quarterTurns: 0)
        let crop = geometry.pixelRect(of: Rect(x: 0.1, y: 0.4, width: 0.5, height: 0.3))
        let letterbox = Letterbox(crop: crop, side: 640)

        let original = Rect(x: 0.2, y: 0.45, width: 0.08, height: 0.06)
        let inModel = letterbox.modelBox(fromFrame: original, crop: crop, frame: geometry.frame)
        let returned = letterbox.frameBox(fromModel: inModel, crop: crop, frame: geometry.frame)

        XCTAssertEqual(returned.x, original.x, accuracy: 1e-9)
        XCTAssertEqual(returned.y, original.y, accuracy: 1e-9)
        XCTAssertEqual(returned.width, original.width, accuracy: 1e-9)
        XCTAssertEqual(returned.height, original.height, accuracy: 1e-9)
    }

    func testTheLetterboxPadsTheShorterSide() {
        // A 960×1080 sweep tile is taller than it is wide, so it is scaled to fit the
        // height and padded left and right.
        let letterbox = Letterbox(crop: PixelRect(x: 0, y: 0, width: 960, height: 1080), side: 640)

        XCTAssertEqual(letterbox.scale, 640.0 / 1080.0, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetY, 0, accuracy: 1e-12)
        XCTAssertGreaterThan(letterbox.offsetX, 0)
        XCTAssertEqual(letterbox.offsetX * 2 + 960 * letterbox.scale, 640, accuracy: 1e-9)
    }

    func testASquareCropIsNotPaddedAtAll() {
        let letterbox = Letterbox(crop: PixelRect(x: 0, y: 0, width: 640, height: 640), side: 640)
        XCTAssertEqual(letterbox.scale, 1, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetX, 0, accuracy: 1e-12)
        XCTAssertEqual(letterbox.offsetY, 0, accuracy: 1e-12)
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter FrameGeometryTests`
Expected: `error: cannot find 'FrameGeometry' in scope`, and the same for `PixelSize`, `PixelPoint`, `PixelRect` and `Letterbox`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/FrameGeometry.swift`:

```swift
import Foundation
import DwarfCore

public struct PixelSize: Equatable, Hashable, Sendable {
    public let width: Int
    public let height: Int

    public init(width: Int, height: Int) {
        self.width = width
        self.height = height
    }
}

public struct PixelPoint: Equatable, Hashable, Sendable {
    public let x: Int
    public let y: Int

    public init(x: Int, y: Int) {
        self.x = x
        self.y = y
    }
}

public struct PixelRect: Equatable, Hashable, Sendable {
    public let x: Int
    public let y: Int
    public let width: Int
    public let height: Int

    public init(x: Int, y: Int, width: Int, height: Int) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }
}

/// Which way is down, and where things are.
///
/// `DwarfCore` reads an animal's ground point as the bottom edge of its box, which is only
/// the ground if down in the image is down in the world. The camera does not know how the
/// phone was bolted into the gnome, so the mount is stated here as a number of quarter
/// turns clockwise applied to the camera buffer to stand the picture upright. A phone lying
/// on its side needs none, which is why that is the mount this project prefers: at 10 fps on
/// an A9, a rotation nobody needs is heat nobody wants.
public struct FrameGeometry: Equatable, Sendable {
    public let buffer: PixelSize
    /// 0, 1, 2 or 3. Values outside that range are taken modulo 4.
    public let quarterTurns: Int
    /// The buffer as `DwarfCore` sees it, after the turns.
    public let frame: PixelSize

    public init(buffer: PixelSize, quarterTurns: Int) {
        self.buffer = buffer
        let turns = ((quarterTurns % 4) + 4) % 4
        self.quarterTurns = turns
        self.frame = turns % 2 == 0
            ? buffer
            : PixelSize(width: buffer.height, height: buffer.width)
    }

    /// Feed these straight into `SchedulerConfig`, never a remembered constant: the crop
    /// rectangles it produces are fractions of exactly this frame, and the app is the only
    /// thing that knows how big the frame really is.
    public func apply(to config: inout SchedulerConfig) {
        config.frameWidthPixels = frame.width
        config.frameHeightPixels = frame.height
    }

    /// Where a pixel of the upright frame lives in the camera's buffer.
    public func bufferPoint(frameX: Int, frameY: Int) -> PixelPoint {
        switch quarterTurns {
        case 1:  return PixelPoint(x: frameY, y: buffer.height - 1 - frameX)
        case 2:  return PixelPoint(x: buffer.width - 1 - frameX, y: buffer.height - 1 - frameY)
        case 3:  return PixelPoint(x: buffer.width - 1 - frameY, y: frameX)
        default: return PixelPoint(x: frameX, y: frameY)
        }
    }

    /// A normalised rectangle in frame coordinates as whole pixels of that same frame,
    /// clamped to it. Clamping rather than refusing, because a crop that runs off the edge
    /// is still a useful crop of what is left.
    public func pixelRect(of rect: Rect) -> PixelRect {
        let left = clamp(rect.x * Double(frame.width), 0, Double(frame.width))
        let top = clamp(rect.y * Double(frame.height), 0, Double(frame.height))
        let right = clamp((rect.x + rect.width) * Double(frame.width), 0, Double(frame.width))
        let bottom = clamp((rect.y + rect.height) * Double(frame.height), 0, Double(frame.height))

        let x = Int(left.rounded(.down))
        let y = Int(top.rounded(.down))
        return PixelRect(x: x, y: y,
                         width: max(1, Int(right.rounded(.up)) - x),
                         height: max(1, Int(bottom.rounded(.up)) - y))
    }

    /// `pixelRect(of:)` for input that may not be trustworthy: a rectangle off a disk file
    /// or a web form. Returns nil rather than a clamped guess when the numbers are not
    /// usable at all.
    public func validPixelRect(of rect: Rect) -> PixelRect? {
        guard rect.x.isFinite, rect.y.isFinite, rect.width.isFinite, rect.height.isFinite,
              rect.width > 0, rect.height > 0 else { return nil }
        let pixels = pixelRect(of: rect)
        guard pixels.x < frame.width, pixels.y < frame.height else { return nil }
        return pixels
    }

    private func clamp(_ v: Double, _ low: Double, _ high: Double) -> Double {
        v.isFinite ? min(max(v, low), high) : low
    }
}

/// How a crop of the frame sits inside the model's square input.
///
/// The model wants a fixed square. Crops are not square — a sweep tile is half the frame,
/// taller than it is wide — so the crop is scaled to fit and the leftover is padded evenly
/// on the two short sides. Every box the model returns has to come back out through the
/// same arithmetic, and a sign error here puts the water a metre from the cat while every
/// test in `DwarfCore` still passes.
public struct Letterbox: Equatable, Sendable {
    /// Crop pixels to model pixels.
    public let scale: Double
    /// Padding on the left, in model pixels. Zero when the crop is wider than it is tall.
    public let offsetX: Double
    /// Padding on the top, in model pixels.
    public let offsetY: Double
    /// The model's input side, 640 unless M0 said otherwise.
    public let side: Int

    public init(crop: PixelRect, side: Int) {
        self.side = side
        let target = Double(side)
        let width = Double(max(crop.width, 1))
        let height = Double(max(crop.height, 1))
        let scale = min(target / width, target / height)
        self.scale = scale
        self.offsetX = (target - width * scale) / 2
        self.offsetY = (target - height * scale) / 2
    }

    /// A box the model returned, normalised to its square input, as a box in normalised
    /// frame coordinates.
    public func frameBox(fromModel box: Rect, crop: PixelRect, frame: PixelSize) -> Rect {
        let target = Double(side)
        let cropX = (box.x * target - offsetX) / scale
        let cropY = (box.y * target - offsetY) / scale
        return Rect(x: (Double(crop.x) + cropX) / Double(frame.width),
                    y: (Double(crop.y) + cropY) / Double(frame.height),
                    width: box.width * target / scale / Double(frame.width),
                    height: box.height * target / scale / Double(frame.height))
    }

    /// The inverse, which exists so the round trip can be tested and so a recorded frame
    /// can be re-cropped later for the dataset.
    public func modelBox(fromFrame box: Rect, crop: PixelRect, frame: PixelSize) -> Rect {
        let target = Double(side)
        let cropX = box.x * Double(frame.width) - Double(crop.x)
        let cropY = box.y * Double(frame.height) - Double(crop.y)
        return Rect(x: (cropX * scale + offsetX) / target,
                    y: (cropY * scale + offsetY) / target,
                    width: box.width * Double(frame.width) * scale / target,
                    height: box.height * Double(frame.height) * scale / target)
    }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter FrameGeometryTests`
Expected: `Executed 9 tests, with 0 failures`.

- [ ] **Step 5: Run the whole suite**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: 10 tests, all passing.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): add frame geometry, letterboxing and the mount's quarter turns"
```

---

## Task 4: Turning camera buffers into something usable

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/FrameConverter.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/FrameConverterTests.swift`

Two conversions, both on the hot path. The camera is asked for `420YpCbCr8BiPlanarFullRange`, which means the luma plane is already a grayscale image and motion detection gets it for nothing. Only the crop that goes to the model needs colour, and only at crop size.

CoreVideo and Accelerate both exist on macOS, so all of this is testable with `swift test`.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/FrameConverterTests.swift`:

```swift
import XCTest
import CoreVideo
import DwarfCore
@testable import DwarfAdapters

final class FrameConverterTests: XCTestCase {
    /// A 420f buffer with a flat luma value, and optionally one brighter rectangle, so a
    /// test can tell where a region ended up after scaling and rotation.
    private func makeBuffer(width: Int = 1920, height: Int = 1080,
                            luma: UInt8 = 40,
                            bright: (x: Int, y: Int, w: Int, h: Int)? = nil,
                            brightLuma: UInt8 = 240) -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        let attributes: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary]
        let status = CVPixelBufferCreate(kCFAllocatorDefault, width, height,
                                         kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
                                         attributes as CFDictionary, &buffer)
        guard status == kCVReturnSuccess, let buffer else {
            fatalError("could not create a test pixel buffer: \(status)")
        }

        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }

        let y = CVPixelBufferGetBaseAddressOfPlane(buffer, 0)!.assumingMemoryBound(to: UInt8.self)
        let yStride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
        for row in 0..<height {
            memset(y.advanced(by: row * yStride), Int32(luma), width)
        }
        if let bright {
            for row in bright.y..<(bright.y + bright.h) {
                memset(y.advanced(by: row * yStride + bright.x), Int32(brightLuma), bright.w)
            }
        }

        // Neutral chroma, so the colour conversion has something defined to do.
        let uv = CVPixelBufferGetBaseAddressOfPlane(buffer, 1)!.assumingMemoryBound(to: UInt8.self)
        let uvStride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 1)
        for row in 0..<(height / 2) {
            memset(uv.advanced(by: row * uvStride), 128, width)
        }
        return buffer
    }

    func testTheGrayFrameKeepsTheFramesAspectRatio() throws {
        // DwarfCore's contract: the small frame and the full frame must describe the same
        // field of view, because blob rectangles from one are used to cut crops from the
        // other.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: makeBuffer()))

        XCTAssertEqual(frame.width, 480)
        XCTAssertEqual(frame.height, 270)
        XCTAssertEqual(Double(frame.width) / Double(frame.height), 1920.0 / 1080.0, accuracy: 0.01)
    }

    func testTheGrayFrameCarriesTheLuma() throws {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: makeBuffer(luma: 90)))
        XCTAssertEqual(frame.meanLuma, 90, accuracy: 2)
    }

    func testAQuarterTurnMovesTheBrightCornerWhereExpected() throws {
        // A bright patch in the buffer's top-left must appear in the frame's bottom-left
        // after one clockwise turn. This is the test that catches a rotation applied the
        // wrong way round, which otherwise only shows up as the gnome aiming at the sky.
        let buffer = makeBuffer(bright: (x: 0, y: 0, w: 400, h: 200))
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 1),
                                       grayLongSide: 480)
        let frame = try XCTUnwrap(converter.gray(from: buffer))

        XCTAssertEqual(frame.width, 270)
        XCTAssertEqual(frame.height, 480)
        XCTAssertGreaterThan(frame.luma(x: 10, y: frame.height - 20), 200)
        XCTAssertLessThan(frame.luma(x: 10, y: 20), 100)
    }

    func testTheGrayLongSideIsHonouredInBothMounts() throws {
        // Portrait must not cost three times the motion-detection work just because the
        // frame got taller. The long side is the budget, whichever way it points.
        let landscape = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let portrait = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                             quarterTurns: 1),
                                      grayLongSide: 480)

        XCTAssertEqual(max(landscape.graySize.width, landscape.graySize.height), 480)
        XCTAssertEqual(max(portrait.graySize.width, portrait.graySize.height), 480)
        XCTAssertEqual(landscape.graySize.width * landscape.graySize.height,
                       portrait.graySize.width * portrait.graySize.height)
    }

    func testTheModelInputIsASquareOfTheRequestedSide() throws {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let crop = PixelRect(x: 100, y: 100, width: 960, height: 1080)
        let input = try XCTUnwrap(converter.modelInput(from: makeBuffer(), cropInFrame: crop, side: 640))

        XCTAssertEqual(CVPixelBufferGetWidth(input), 640)
        XCTAssertEqual(CVPixelBufferGetHeight(input), 640)
        XCTAssertEqual(CVPixelBufferGetPixelFormatType(input), kCVPixelFormatType_32BGRA)
    }

    func testTheModelInputPadsRatherThanStretches() throws {
        // A tall crop letterboxed into a square must have padding down its sides, and the
        // padding must be the value the model was trained to ignore rather than black.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let crop = PixelRect(x: 0, y: 0, width: 540, height: 1080)
        let input = try XCTUnwrap(converter.modelInput(from: makeBuffer(luma: 200),
                                                       cropInFrame: crop, side: 640))

        CVPixelBufferLockBaseAddress(input, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(input, .readOnly) }
        let base = CVPixelBufferGetBaseAddress(input)!.assumingMemoryBound(to: UInt8.self)
        let stride = CVPixelBufferGetBytesPerRow(input)

        // Far left column: padding. Centre: image.
        let leftBlue = base[320 * stride + 0]
        let centreBlue = base[320 * stride + 320 * 4]
        XCTAssertEqual(leftBlue, FrameConverter.padding)
        XCTAssertNotEqual(centreBlue, FrameConverter.padding)
    }

    func testAnEmptyOrImpossibleCropIsRefusedRatherThanCrashing() {
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        let buffer = makeBuffer()
        XCTAssertNil(converter.modelInput(from: buffer,
                                          cropInFrame: PixelRect(x: 0, y: 0, width: 0, height: 100),
                                          side: 640))
        XCTAssertNil(converter.modelInput(from: buffer,
                                          cropInFrame: PixelRect(x: 5000, y: 0, width: 100, height: 100),
                                          side: 640))
    }

    func testAWronglySizedBufferIsRefused() {
        // The geometry was built for 1920×1080. If the capture session ever hands over
        // something else, every crop rectangle computed from it is wrong, and saying so is
        // better than quietly cropping the wrong part of the garden.
        let converter = FrameConverter(geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                                              quarterTurns: 0),
                                       grayLongSide: 480)
        XCTAssertNil(converter.gray(from: makeBuffer(width: 1280, height: 720)))
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter FrameConverterTests`
Expected: `error: cannot find 'FrameConverter' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/FrameConverter.swift`:

```swift
import Foundation
import CoreVideo
import Accelerate
import DwarfCore

/// Camera buffers in, the two things the pipeline actually wants out.
///
/// The capture session is configured for `420YpCbCr8BiPlanarFullRange`, which is the
/// camera's native format, so no conversion happens at capture time and plane 0 is already
/// the grayscale image motion detection needs. Colour is produced only for the crop handed
/// to the model, and only at crop size — on an A9 with no Neural Engine, converting a whole
/// 1080p frame to RGB ten times a second is heat spent on pixels nothing will ever read.
public final class FrameConverter {
    /// What the letterbox is filled with. 114 is the value Ultralytics pads with, so the
    /// model has seen this exact grey around its training images.
    public static let padding: UInt8 = 114

    public let geometry: FrameGeometry
    /// Size of the motion-detection frame, in frame orientation.
    public let graySize: PixelSize

    private let grayLongSide: Int

    public init(geometry: FrameGeometry, grayLongSide: Int = 480) {
        self.geometry = geometry
        self.grayLongSide = grayLongSide

        // The long side is the budget, so portrait costs the same as landscape rather than
        // scaling with whichever way the phone was bolted in.
        let frame = geometry.frame
        let long = max(frame.width, frame.height)
        let short = min(frame.width, frame.height)
        let scaledShort = max(1, Int((Double(grayLongSide) * Double(short) / Double(long)).rounded()))
        self.graySize = frame.width >= frame.height
            ? PixelSize(width: grayLongSide, height: scaledShort)
            : PixelSize(width: scaledShort, height: grayLongSide)
    }

    // MARK: motion

    /// The luma plane, scaled down and stood upright.
    public func gray(from pixelBuffer: CVPixelBuffer) -> GrayFrame? {
        guard CVPixelBufferGetWidth(pixelBuffer) == geometry.buffer.width,
              CVPixelBufferGetHeight(pixelBuffer) == geometry.buffer.height else { return nil }
        guard CVPixelBufferGetPlaneCount(pixelBuffer) >= 1 else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else { return nil }

        var source = vImage_Buffer(data: base,
                                   height: vImagePixelCount(geometry.buffer.height),
                                   width: vImagePixelCount(geometry.buffer.width),
                                   rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0))

        // Scale in buffer orientation, then turn: scaling first means the rotation moves a
        // few hundred kilobytes rather than two megabytes.
        let scaledWidth = geometry.quarterTurns % 2 == 0 ? graySize.width : graySize.height
        let scaledHeight = geometry.quarterTurns % 2 == 0 ? graySize.height : graySize.width

        var scaled = [UInt8](repeating: 0, count: scaledWidth * scaledHeight)
        var scaleError = kvImageNoError
        scaled.withUnsafeMutableBytes { raw in
            var destination = vImage_Buffer(data: raw.baseAddress,
                                            height: vImagePixelCount(scaledHeight),
                                            width: vImagePixelCount(scaledWidth),
                                            rowBytes: scaledWidth)
            scaleError = vImageScale_Planar8(&source, &destination, nil, vImage_Flags(kvImageNoFlags))
        }
        guard scaleError == kvImageNoError else { return nil }

        guard let upright = rotated(planar: scaled, width: scaledWidth, height: scaledHeight) else {
            return nil
        }
        return GrayFrame(validating: graySize.width, height: graySize.height, pixels: upright)
    }

    private func rotated(planar pixels: [UInt8], width: Int, height: Int) -> [UInt8]? {
        guard geometry.quarterTurns != 0 else { return pixels }

        let constant: UInt8
        switch geometry.quarterTurns {
        case 1: constant = UInt8(kRotate90DegreesClockwise)
        case 2: constant = UInt8(kRotate180DegreesClockwise)
        default: constant = UInt8(kRotate270DegreesClockwise)
        }

        var output = [UInt8](repeating: 0, count: pixels.count)
        var source = pixels
        var error = kvImageNoError
        source.withUnsafeMutableBytes { sourceRaw in
            var input = vImage_Buffer(data: sourceRaw.baseAddress,
                                      height: vImagePixelCount(height),
                                      width: vImagePixelCount(width),
                                      rowBytes: width)
            output.withUnsafeMutableBytes { outputRaw in
                var destination = vImage_Buffer(data: outputRaw.baseAddress,
                                                height: vImagePixelCount(width),
                                                width: vImagePixelCount(height),
                                                rowBytes: height)
                error = vImageRotate90_Planar8(&input, &destination, constant, 0,
                                               vImage_Flags(kvImageNoFlags))
            }
        }
        return error == kvImageNoError ? output : nil
    }

    // MARK: detection

    /// One crop of the frame, in colour, letterboxed into the square the model wants.
    ///
    /// `cropInFrame` is in upright frame pixels — the same coordinates `FrameGeometry`
    /// produced it in — and is mapped back into the camera's buffer here.
    public func modelInput(from pixelBuffer: CVPixelBuffer, cropInFrame crop: PixelRect,
                           side: Int) -> CVPixelBuffer? {
        guard crop.width > 0, crop.height > 0, side > 0 else { return nil }
        guard crop.x >= 0, crop.y >= 0,
              crop.x + crop.width <= geometry.frame.width,
              crop.y + crop.height <= geometry.frame.height else { return nil }
        guard CVPixelBufferGetWidth(pixelBuffer) == geometry.buffer.width,
              CVPixelBufferGetHeight(pixelBuffer) == geometry.buffer.height else { return nil }

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }

        guard var colour = bgra(from: pixelBuffer) else { return nil }
        defer { free(colour.data) }

        // The crop's two opposite corners, carried into buffer space. A rotation keeps a
        // rectangle a rectangle; it just may arrive with its corners swapped.
        let a = geometry.bufferPoint(frameX: crop.x, frameY: crop.y)
        let b = geometry.bufferPoint(frameX: crop.x + crop.width - 1,
                                     frameY: crop.y + crop.height - 1)
        let originX = min(a.x, b.x)
        let originY = min(a.y, b.y)
        let regionWidth = abs(b.x - a.x) + 1
        let regionHeight = abs(b.y - a.y) + 1

        var region = vImage_Buffer(
            data: colour.data.advanced(by: originY * colour.rowBytes + originX * 4),
            height: vImagePixelCount(regionHeight),
            width: vImagePixelCount(regionWidth),
            rowBytes: colour.rowBytes)

        guard var upright = rotatedColour(&region, width: regionWidth, height: regionHeight) else {
            return nil
        }
        defer { if geometry.quarterTurns != 0 { free(upright.data) } }

        return letterboxed(&upright, side: side)
    }

    private func bgra(from pixelBuffer: CVPixelBuffer) -> vImage_Buffer? {
        let width = geometry.buffer.width
        let height = geometry.buffer.height
        guard let yBase = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0),
              let uvBase = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1) else { return nil }

        var luma = vImage_Buffer(data: yBase, height: vImagePixelCount(height),
                                 width: vImagePixelCount(width),
                                 rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0))
        var chroma = vImage_Buffer(data: uvBase, height: vImagePixelCount(height / 2),
                                   width: vImagePixelCount(width / 2),
                                   rowBytes: CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1))

        var destination = vImage_Buffer()
        guard vImageBuffer_Init(&destination, vImagePixelCount(height), vImagePixelCount(width),
                                32, vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }

        var info = vImage_YpCbCrToARGB()
        var pixelRange = vImage_YpCbCrPixelRange(Yp_bias: 0, CbCr_bias: 128, YpRangeMax: 255,
                                                 CbCrRangeMax: 255, YpMax: 255, YpMin: 0,
                                                 CbCrMax: 255, CbCrMin: 0)
        guard vImageConvert_YpCbCrToARGB_GenerateConversion(
                kvImage_YpCbCrToARGBMatrix_ITU_R_601_4, &pixelRange, &info,
                kvImage420Yp8_CbCr8, kvImageARGB8888,
                vImage_Flags(kvImageNoFlags)) == kvImageNoError else {
            free(destination.data)
            return nil
        }

        // The map puts the channels in BGRA order, which is what CoreML's image input and
        // every debugging tool expect.
        let map: [UInt8] = [3, 2, 1, 0]
        guard vImageConvert_420Yp8_CbCr8ToARGB8888(&luma, &chroma, &destination, &info, map, 255,
                                                   vImage_Flags(kvImageNoFlags)) == kvImageNoError else {
            free(destination.data)
            return nil
        }
        return destination
    }

    private func rotatedColour(_ region: inout vImage_Buffer, width: Int,
                               height: Int) -> vImage_Buffer? {
        guard geometry.quarterTurns != 0 else { return region }

        let constant: UInt8
        switch geometry.quarterTurns {
        case 1: constant = UInt8(kRotate90DegreesClockwise)
        case 2: constant = UInt8(kRotate180DegreesClockwise)
        default: constant = UInt8(kRotate270DegreesClockwise)
        }

        let turnedWidth = geometry.quarterTurns % 2 == 0 ? width : height
        let turnedHeight = geometry.quarterTurns % 2 == 0 ? height : width

        var destination = vImage_Buffer()
        guard vImageBuffer_Init(&destination, vImagePixelCount(turnedHeight),
                                vImagePixelCount(turnedWidth), 32,
                                vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }

        var background: [UInt8] = [FrameConverter.padding, FrameConverter.padding,
                                   FrameConverter.padding, 255]
        let error = vImageRotate90_ARGB8888(&region, &destination, constant, &background,
                                            vImage_Flags(kvImageNoFlags))
        guard error == kvImageNoError else {
            free(destination.data)
            return nil
        }
        return destination
    }

    private func letterboxed(_ region: inout vImage_Buffer, side: Int) -> CVPixelBuffer? {
        let box = Letterbox(crop: PixelRect(x: 0, y: 0, width: Int(region.width),
                                            height: Int(region.height)),
                            side: side)
        let innerWidth = max(1, Int((Double(region.width) * box.scale).rounded()))
        let innerHeight = max(1, Int((Double(region.height) * box.scale).rounded()))

        var output: CVPixelBuffer?
        let attributes: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:] as CFDictionary]
        guard CVPixelBufferCreate(kCFAllocatorDefault, side, side, kCVPixelFormatType_32BGRA,
                                  attributes as CFDictionary, &output) == kCVReturnSuccess,
              let output else { return nil }

        CVPixelBufferLockBaseAddress(output, [])
        defer { CVPixelBufferUnlockBaseAddress(output, []) }
        guard let base = CVPixelBufferGetBaseAddress(output) else { return nil }
        let rowBytes = CVPixelBufferGetBytesPerRow(output)

        // Fill first, so whatever the scale does not cover is the padding value the model
        // was trained against rather than uninitialised memory.
        for row in 0..<side {
            memset(base.advanced(by: row * rowBytes), Int32(FrameConverter.padding), side * 4)
        }

        let insetX = Int(box.offsetX.rounded())
        let insetY = Int(box.offsetY.rounded())
        var destination = vImage_Buffer(
            data: base.advanced(by: insetY * rowBytes + insetX * 4),
            height: vImagePixelCount(innerHeight),
            width: vImagePixelCount(innerWidth),
            rowBytes: rowBytes)

        guard vImageScale_ARGB8888(&region, &destination, nil,
                                   vImage_Flags(kvImageNoFlags)) == kvImageNoError else { return nil }
        return output
    }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter FrameConverterTests`
Expected: `Executed 8 tests, with 0 failures`.

- [ ] **Step 5: Measure it, because this runs ten times a second**

Write a throwaway release-mode measurement — not a committed test — that converts 200 frames and reports the mean per-frame cost of `gray(from:)` and of `modelInput(from:cropInFrame:side:)` for a 640×640 crop and for a 960×1080 sweep tile:

```bash
cd ios/DwarfApp/DwarfAdapters && swift test -c release --filter FrameConverterTests
```

Report the numbers. A Mac is much faster than an A9, so these are a floor, not a prediction — but if the gray conversion is not comfortably under a millisecond here, it will not fit in the budget there, and the fix is `grayLongSide` rather than cleverness.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): convert camera buffers to gray frames and model inputs"
```

---

## Task 5: The detector and its box decoding

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Detector.swift`
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/CoreMLDetector.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/DetectorTests.swift`

The model's two output tensors turned into `DwarfCore.Detection` values in frame coordinates. The decoding is a pure function and is tested here; the model itself is only exercised on the phone, in Task 6.

`DwarfCore` documents that everything reaching `Detection` is treated as a cat. That filtering happens here, and nowhere else.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/DetectorTests.swift`:

```swift
import XCTest
import CoreML
import DwarfCore
@testable import DwarfAdapters

final class DetectorTests: XCTestCase {
    /// The shape Ultralytics' CoreML export with embedded NMS produces: confidences per
    /// class, and boxes as centre/size normalised to the model's square input.
    private func outputs(_ rows: [(cls: Int, confidence: Double, box: [Double])])
        throws -> (MLMultiArray, MLMultiArray) {
        let confidence = try MLMultiArray(shape: [NSNumber(value: rows.count), 80],
                                          dataType: .double)
        let coordinates = try MLMultiArray(shape: [NSNumber(value: rows.count), 4],
                                           dataType: .double)
        for i in 0..<(rows.count * 80) { confidence[i] = 0 }
        for (row, entry) in rows.enumerated() {
            confidence[row * 80 + entry.cls] = NSNumber(value: entry.confidence)
            for k in 0..<4 { coordinates[row * 4 + k] = NSNumber(value: entry.box[k]) }
        }
        return (confidence, coordinates)
    }

    func testACentreSizeBoxBecomesACornerBox() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.9, box: [0.5, 0.5, 0.2, 0.4])
        ])
        let boxes = BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                      minConfidence: 0.25)

        XCTAssertEqual(boxes.count, 1)
        XCTAssertEqual(boxes[0].box.x, 0.4, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.y, 0.3, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.width, 0.2, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].box.height, 0.4, accuracy: 1e-9)
        XCTAssertEqual(boxes[0].confidence, 0.9, accuracy: 1e-9)
    }

    func testOnlyCatsSurvive() throws {
        // DwarfCore treats everything it is handed as a cat. A dog at 0.99 that reaches it
        // is a dog that gets sprayed.
        let (confidence, coordinates) = try outputs([
            (cls: 16, confidence: 0.99, box: [0.5, 0.5, 0.2, 0.2]),   // dog
            (cls: 0,  confidence: 0.95, box: [0.2, 0.2, 0.1, 0.1]),   // person
            (cls: BoxDecoder.catClassIndex, confidence: 0.6, box: [0.8, 0.8, 0.1, 0.1])
        ])
        let boxes = BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                      minConfidence: 0.25)

        XCTAssertEqual(boxes.count, 1)
        XCTAssertEqual(boxes[0].confidence, 0.6, accuracy: 1e-9)
    }

    func testLowConfidenceRowsAreDropped() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.1, box: [0.5, 0.5, 0.2, 0.2])
        ])
        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testMismatchedOrEmptyTensorsAreSurvivable() throws {
        // A model swapped for a different export should produce no detections, not a crash
        // in the middle of the garden.
        let confidence = try MLMultiArray(shape: [2, 80], dataType: .double)
        let coordinates = try MLMultiArray(shape: [1, 4], dataType: .double)
        for i in 0..<160 { confidence[i] = 0 }
        for i in 0..<4 { coordinates[i] = 0 }

        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testANonFiniteBoxIsDropped() throws {
        let (confidence, coordinates) = try outputs([
            (cls: BoxDecoder.catClassIndex, confidence: 0.9,
             box: [Double.nan, 0.5, 0.2, 0.2])
        ])
        // A NaN that reaches DwarfCore poisons the tracker's distances, and every
        // comparison against it is false in a way that reads as "in range".
        XCTAssertTrue(BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                        minConfidence: 0.25).isEmpty)
    }

    func testTheFakeDetectorReturnsWhatItWasGiven() throws {
        // The fake exists so later tasks can drive a whole runtime without a model.
        let fake = FakeDetector()
        fake.next = [RawBox(box: Rect(x: 0.1, y: 0.1, width: 0.2, height: 0.2), confidence: 0.8)]
        let buffer = try XCTUnwrap(FakeDetector.blankInput(side: 64))

        XCTAssertEqual(try fake.detect(input: buffer).count, 1)
        XCTAssertEqual(fake.calls, 1)
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter DetectorTests`
Expected: `error: cannot find 'BoxDecoder' in scope`.

- [ ] **Step 3: Write the protocol and the decoder**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Detector.swift`:

```swift
import Foundation
import CoreML
import CoreVideo
import DwarfCore

/// One box as the model gave it, normalised to the model's square input. Turning this into
/// frame coordinates is `Letterbox`'s job, and it needs to know which crop it came from.
public struct RawBox: Equatable, Sendable {
    public let box: Rect
    public let confidence: Double

    public init(box: Rect, confidence: Double) {
        self.box = box
        self.confidence = confidence
    }
}

public enum DetectorError: Error, Equatable {
    case modelMissing(name: String)
    case unexpectedOutputs
}

/// Anything that can look at a square image and say where the cats are.
public protocol Detector: AnyObject {
    /// Blocking. Callers run this off the capture queue.
    func detect(input: CVPixelBuffer) throws -> [RawBox]
}

/// Reads Ultralytics' CoreML export.
///
/// The export with `nms=True` produces two tensors: `confidence`, shaped rows × 80, one
/// column per COCO class, and `coordinates`, shaped rows × 4, each row being centre x,
/// centre y, width and height normalised to the model's square input. Non-maximum
/// suppression has already happened inside the model, so every row is a distinct object.
public enum BoxDecoder {
    /// COCO's class order: person 0, …, bird 14, cat 15, dog 16.
    public static let catClassIndex = 15

    public static func decode(confidence: MLMultiArray, coordinates: MLMultiArray,
                              minConfidence: Double) -> [RawBox] {
        guard confidence.shape.count == 2, coordinates.shape.count == 2 else { return [] }
        let rows = confidence.shape[0].intValue
        let classes = confidence.shape[1].intValue
        guard coordinates.shape[0].intValue == rows,
              coordinates.shape[1].intValue == 4,
              classes > catClassIndex else { return [] }

        var boxes: [RawBox] = []
        boxes.reserveCapacity(rows)
        for row in 0..<rows {
            let score = confidence[row * classes + catClassIndex].doubleValue
            guard score >= minConfidence else { continue }

            let centreX = coordinates[row * 4 + 0].doubleValue
            let centreY = coordinates[row * 4 + 1].doubleValue
            let width = coordinates[row * 4 + 2].doubleValue
            let height = coordinates[row * 4 + 3].doubleValue

            // A non-finite box poisons every distance the tracker computes, and comparisons
            // against NaN are false in a way that reads as "not too close". Dropping the
            // row costs one look; letting it through costs the guarantee.
            guard centreX.isFinite, centreY.isFinite, width.isFinite, height.isFinite,
                  width > 0, height > 0, score.isFinite else { continue }

            boxes.append(RawBox(box: Rect(x: centreX - width / 2, y: centreY - height / 2,
                                          width: width, height: height),
                                confidence: score))
        }
        return boxes
    }
}

/// A detector that answers with whatever it was told to, so a runtime can be driven end to
/// end on a Mac.
public final class FakeDetector: Detector {
    public var next: [RawBox] = []
    public private(set) var calls = 0
    /// Set to have `detect` throw, for testing what a failed inference does to the loop.
    public var error: Error?

    public init() {}

    public func detect(input: CVPixelBuffer) throws -> [RawBox] {
        calls += 1
        if let error { throw error }
        return next
    }

    /// A blank square, for tests that need an input to hand over.
    public static func blankInput(side: Int) -> CVPixelBuffer? {
        var buffer: CVPixelBuffer?
        guard CVPixelBufferCreate(kCFAllocatorDefault, side, side, kCVPixelFormatType_32BGRA,
                                  nil, &buffer) == kCVReturnSuccess else { return nil }
        return buffer
    }
}
```

- [ ] **Step 4: Write the real detector**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/CoreMLDetector.swift`:

```swift
import Foundation
import CoreML
import CoreVideo

/// The exported YOLO11n, loaded from the app bundle.
///
/// Deliberately thin: it feeds a pixel buffer in and hands the two output tensors to
/// `BoxDecoder`. Everything worth arguing about is in the decoder, which is tested on a
/// Mac; what is left here can only be exercised on the phone, and Task 6 does that.
public final class CoreMLDetector: Detector {
    private let model: MLModel
    private let imageInputName: String
    private let minConfidence: Double
    private let iouThreshold: Double

    /// - Parameter computeUnits: the A9 has no Neural Engine, so `.all` means GPU with a
    ///   CPU fallback. Left configurable because M0 may find the CPU steadier under
    ///   thermal pressure than a GPU competing with the camera.
    public init(modelName: String = "yolo11n", bundle: Bundle = .main,
                minConfidence: Double = 0.25, iouThreshold: Double = 0.45,
                computeUnits: MLComputeUnits = .all) throws {
        guard let url = bundle.url(forResource: modelName, withExtension: "mlmodelc") else {
            throw DetectorError.modelMissing(name: modelName)
        }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = computeUnits
        self.model = try MLModel(contentsOf: url, configuration: configuration)
        self.minConfidence = minConfidence
        self.iouThreshold = iouThreshold

        // The export has three inputs, not one: `image`, `iouThreshold` and
        // `confidenceThreshold`. Picking `keys.first` would hand a pixel buffer to
        // whichever of them a Dictionary happened to enumerate first — a bug that works
        // on the bench and fails in the garden, or the other way round. Select by type.
        let inputs = model.modelDescription.inputDescriptionsByName
        guard let image = inputs.first(where: { $0.value.type == .image })?.key else {
            throw DetectorError.unexpectedOutputs
        }
        self.imageInputName = image
    }

    public func detect(input: CVPixelBuffer) throws -> [RawBox] {
        // None of the three inputs is optional in the spec, so all three are supplied.
        // Thresholding inside the model is also cheaper: suppressed boxes never become
        // rows for BoxDecoder to walk. It still checks the confidence itself, because a
        // re-export with different defaults should not quietly widen what gets fired at.
        let features = try MLDictionaryFeatureProvider(dictionary: [
            imageInputName: MLFeatureValue(pixelBuffer: input),
            "iouThreshold": MLFeatureValue(double: iouThreshold),
            "confidenceThreshold": MLFeatureValue(double: minConfidence)
        ])
        let output = try model.prediction(from: features)

        guard let confidence = output.featureValue(for: "confidence")?.multiArrayValue,
              let coordinates = output.featureValue(for: "coordinates")?.multiArrayValue else {
            throw DetectorError.unexpectedOutputs
        }
        return BoxDecoder.decode(confidence: confidence, coordinates: coordinates,
                                 minConfidence: minConfidence)
    }
}
```

- [ ] **Step 5: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 24 tests, with 0 failures`.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): decode the model's boxes and keep only cats"
```

---

## Task 6: M0 — is the phone fast enough? (HARDWARE: the iPhone)

**Files:**
- Create: `ios/DwarfApp/App/BenchmarkView.swift`
- Modify: `ios/DwarfApp/App/RootView.swift`

The spec's first milestone, and the one that decides the cycle budget for everything after it: **YOLO11n at 640 must sustain at least 3 inferences per second for ten minutes without the phone reaching `serious` thermal state.** If it cannot, the fallbacks in order are FP16 weights, then `imgsz` 416, then 320 — and the tasks after this one inherit whatever number comes out.

This task needs the phone. Nothing here can be verified on a Mac.

- [ ] **Step 1: Write the benchmark screen**

Create `ios/DwarfApp/App/BenchmarkView.swift`:

```swift
import SwiftUI
import CoreVideo
import DwarfAdapters

/// Runs the model over a synthetic input as fast as it can, and reports what the phone
/// actually sustains. Synthetic on purpose: this measures the model and the thermals, not
/// the camera, and a fixed input makes two runs comparable.
struct BenchmarkView: View {
    @State private var line = "idle"
    @State private var running = false

    var body: some View {
        VStack(spacing: 16) {
            Text("M0 — inference benchmark").font(.headline)
            Text(line).font(.system(.body, design: .monospaced)).multilineTextAlignment(.center)
            Button(running ? "running…" : "run for 10 minutes") { start() }
                .disabled(running)
        }
        .padding()
    }

    private func start() {
        running = true
        Task.detached(priority: .userInitiated) {
            await run()
        }
    }

    private func run() async {
        guard let detector = try? CoreMLDetector(), let input = FakeDetector.blankInput(side: 640) else {
            await report("could not load the model")
            return
        }

        let started = ProcessInfo.processInfo.systemUptime
        var count = 0
        var worstThermal = ProcessInfo.processInfo.thermalState
        var lastReport = started

        while ProcessInfo.processInfo.systemUptime - started < 600 {
            _ = try? detector.detect(input: input)
            count += 1

            let state = ProcessInfo.processInfo.thermalState
            if state.rawValue > worstThermal.rawValue { worstThermal = state }

            let now = ProcessInfo.processInfo.systemUptime
            if now - lastReport >= 5 {
                lastReport = now
                let rate = Double(count) / (now - started)
                await report(String(format: "%.0f s · %d inferences · %.2f /s · thermal %d",
                                    now - started, count, rate, worstThermal.rawValue))
            }
        }

        let elapsed = ProcessInfo.processInfo.systemUptime - started
        await report(String(format: "DONE %.0f s · %d inferences · %.2f /s · worst thermal %d",
                            elapsed, count, Double(count) / elapsed, worstThermal.rawValue))
    }

    @MainActor private func report(_ text: String) {
        line = text
        if text.hasPrefix("DONE") || text.hasPrefix("could not") { running = false }
    }
}
```

- [ ] **Step 2: Show it**

Replace the body of `RootView` with:

```swift
struct RootView: View {
    var body: some View {
        BenchmarkView()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
            .foregroundStyle(.white)
    }
}
```

- [ ] **Step 3: Make sure the model is in the target**

`project.yml` already declares `sources: [{ path: App }]`, and `App/Models/yolo11n.mlpackage` sits underneath it, so XcodeGen picks it up and Xcode compiles it to `yolo11n.mlmodelc` in the bundle. Regenerate and rebuild:

```bash
cd ios/DwarfApp && xcodegen generate
xcodebuild -project DwarfApp.xcodeproj -scheme DwarfApp -sdk iphoneos -configuration Release build CODE_SIGNING_ALLOWED=NO
```

Expected: `** BUILD SUCCEEDED **`, and `yolo11n.mlmodelc` present in the built `.app`. Check it, because a model that silently failed to compile shows up as "could not load the model" on the phone and wastes a bench session:

```bash
find ~/Library/Developer/Xcode/DerivedData -name "yolo11n.mlmodelc" -maxdepth 8 | head
```

Release, not Debug: a Debug build measures the wrong thing.

- [ ] **Step 4: Get it onto the phone**

Package the `.app` as a `.tipa` and install through TrollStore:

```bash
cd <the built products directory>
mkdir -p Payload && cp -R DwarfApp.app Payload/
zip -qr DwarfApp.tipa Payload
```

Transfer the `.tipa` to the phone and open it with TrollStore. Then on the phone: Settings → Display → Auto-Lock → Never, Low Power Mode off, brightness at minimum.

- [ ] **Step 5: Run it and write down the answer**

Run the ten-minute benchmark with the phone lying flat, screen on, **not** charging — charging adds heat the real gnome will also have, but this measurement is about the model, and the charger's contribution is measured separately in M4.

Record: inferences per second, worst thermal state (0 nominal, 1 fair, 2 serious, 3 critical), and whether the rate was stable or decayed.

- [ ] **Step 6: Decide, and write the decision into this plan**

- **≥ 3 /s and thermal ≤ 1**: keep `imgsz` 640. Nothing changes.
- **Short of it**: re-export with `--half` and repeat. Then `--imgsz 416`, then `320`. Each drop costs range — a cat 75 px long at 6 m in 1080p is roughly 25 px at 320 — so stop at the first size that holds.
- **Still short at 320**: stop and re-plan. The cycle budget in `SchedulerConfig` and the whole premise of two crops plus a sweep tile per cycle would need rethinking, and that is a spec conversation, not an implementation detail.

Append the result to this task as a note, commit it, and carry the number into Task 12's `SchedulerConfig`.

- [ ] **Step 7: Commit**

```bash
git add ios/DwarfApp docs/superpowers/plans/2026-09-22-dwarfapp-runtime.md
git commit -m "feat(app): add the M0 inference benchmark and record its result"
```

---

## Task 7: Clocks

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Clock.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/ClockTests.swift`

`DwarfCore` measures every cooldown, cap and stillness window on `uptime` and requires it to
be monotonic. This is the bullet of its contract that says so, made into code: the app cannot
simply promise to be well-behaved, because `ProcessInfo.systemUptime` does not advance while
a device sleeps, and a phone that sleeps and wakes hands back a clock that has effectively
jumped.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/ClockTests.swift`:

```swift
import XCTest
@testable import DwarfAdapters

final class ClockTests: XCTestCase {
    func testTheSystemClockMovesForward() {
        let clock = SystemClock()
        let first = clock.uptime
        // Busy-wait rather than sleep: this asserts the clock advances, not that the test
        // runner can nap.
        while clock.uptime == first {}
        XCTAssertGreaterThan(clock.uptime, first)
    }

    func testASteadyClockPassesAWellBehavedClockThrough() {
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 10
        XCTAssertEqual(clock.uptime, 10, accuracy: 1e-9)
        raw.uptime = 11.5
        XCTAssertEqual(clock.uptime, 11.5, accuracy: 1e-9)
        XCTAssertEqual(clock.anomalies, 0)
    }

    func testASteadyClockNeverGoesBackwards() {
        // The failure this exists for: a rewound uptime makes every "how long since" answer
        // negative, so cooldowns look expired and caps look empty. The gnome would fire
        // again immediately.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 100
        _ = clock.uptime
        raw.uptime = 40

        XCTAssertGreaterThanOrEqual(clock.uptime, 100)
        XCTAssertEqual(clock.anomalies, 1)
        XCTAssertEqual(clock.worstRewind, 60, accuracy: 1e-9)
    }

    func testTimeKeepsMovingAfterARewind() {
        // Holding the last value would stop time altogether, and a cooldown that never
        // expires is its own kind of broken. The offset carries on from where it was.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)

        raw.uptime = 100
        _ = clock.uptime
        raw.uptime = 0
        let atRewind = clock.uptime
        raw.uptime = 5

        XCTAssertEqual(clock.uptime - atRewind, 5, accuracy: 1e-9)
    }

    func testTheWallClockIsPassedStraightThrough() {
        // now is used for exactly one thing — the active-hours window — and a jump there
        // is a timezone change or daylight saving, which is information, not corruption.
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)
        let moment = Date(timeIntervalSince1970: 1_780_000_000)
        raw.now = moment
        XCTAssertEqual(clock.now, moment)
    }

    func testANonFiniteRawUptimeIsRefused() {
        let raw = TestClock()
        let clock = SteadyClock(wrapping: raw)
        raw.uptime = 50
        _ = clock.uptime
        raw.uptime = .nan

        XCTAssertEqual(clock.uptime, 50, accuracy: 1e-9)
        XCTAssertEqual(clock.anomalies, 1)
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter ClockTests`
Expected: `error: cannot find 'SystemClock' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Clock.swift`:

```swift
import Foundation

/// The two clocks the pipeline runs on, kept apart on purpose.
public protocol Clock: AnyObject {
    /// Monotonic seconds. Every interval `DwarfCore` measures is on this one.
    var uptime: TimeInterval { get }
    /// Wall clock. Used for the active-hours window and nothing else, so daylight saving
    /// cannot reach a cooldown.
    var now: Date { get }
}

public final class SystemClock: Clock {
    public init() {}

    /// `systemUptime` is unaffected by the wall clock being set, which `Date` is not. It
    /// does not advance while the device is asleep — for a gnome that is plugged in with
    /// the idle timer disabled that should never happen, and `SteadyClock` is what catches
    /// it when it does anyway.
    public var uptime: TimeInterval { ProcessInfo.processInfo.systemUptime }
    public var now: Date { Date() }
}

public final class TestClock: Clock {
    public var uptime: TimeInterval = 0
    public var now: Date = Date(timeIntervalSince1970: 1_780_000_000)
    public init() {}
}

/// A clock that will not go backwards, whatever it is wrapping.
///
/// `DwarfCore` documents that a misbehaving uptime "fails safe", but only because the app is
/// trusted to supply a good one. This is where that trust is made real. A rewind is carried
/// forward as an offset rather than frozen: holding the last value would stop time, and a
/// cooldown that never expires is as broken as one that expires instantly, just quieter.
public final class SteadyClock: Clock {
    private let wrapped: Clock
    private var offset: TimeInterval = 0
    private var lastRaw: TimeInterval?
    private var lastReported: TimeInterval = 0

    /// How many times the underlying clock misbehaved. Surfaced in the status screen,
    /// because a phone whose clock jumps is a phone with a bigger problem.
    public private(set) var anomalies = 0
    /// The largest single step backwards seen, in seconds.
    public private(set) var worstRewind: TimeInterval = 0

    public init(wrapping clock: Clock) {
        self.wrapped = clock
    }

    public var uptime: TimeInterval {
        let raw = wrapped.uptime

        guard raw.isFinite else {
            anomalies += 1
            return lastReported
        }

        if let last = lastRaw, raw < last {
            let rewind = last - raw
            anomalies += 1
            worstRewind = max(worstRewind, rewind)
            offset += rewind
        }

        lastRaw = raw
        lastReported = raw + offset
        return lastReported
    }

    public var now: Date { wrapped.now }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 30 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): guarantee the monotonic clock DwarfCore relies on"
```

---

## Task 8: The link to the gnome

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Transport.swift`
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/ActuatorLink.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/ActuatorLinkTests.swift`

Everything about talking to the ESP32 except the radio itself: the heartbeat that keeps it
armed, reassembling messages, decoding status, and — the part that matters most — deciding
when a status is too old to be believed.

This is the contract bullet that says to pass `nil` for `status` the moment the link's health
is in doubt. `FirePolicy` has no notion of how old a status is, so if the app hands back a
cached one after the link dies, it keeps authorising shots. The firmware's own watchdog means
those shots are refused rather than fired, but each one still spends the animal's budget on
water it never received.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/ActuatorLinkTests.swift`:

```swift
import XCTest
import DwarfCore
@testable import DwarfAdapters

final class ActuatorLinkTests: XCTestCase {
    private func healthyStatus() -> Data {
        Data("""
        {"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":true,"charge":false,\
        "fan":false,"temp":22,"fault":null,"shots":3}
        """.utf8)
    }

    private func makeLink() -> (ActuatorLink, FakeTransport) {
        let transport = FakeTransport()
        return (ActuatorLink(transport: transport), transport)
    }

    func testTheHeartbeatGoesOutOnSchedule() {
        let (link, transport) = makeLink()
        transport.isConnected = true

        link.tick(uptime: 0)
        link.tick(uptime: 0.5)
        link.tick(uptime: 1.1)

        let beats = transport.sentStrings.filter { $0.contains("\"hb\"") }
        XCTAssertEqual(beats.count, 2, "one at zero, one past the interval: \(transport.sentStrings)")
    }

    func testNoHeartbeatGoesOutWhileDisconnected() {
        // Writing into a dead transport is how a queue backs up and then floods the moment
        // the link returns.
        let (link, transport) = makeLink()
        transport.isConnected = false
        link.tick(uptime: 0)
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testAStatusIsDecodedAndOffered() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)

        let status = try XCTUnwrap(link.status(asOf: 10.5))
        XCTAssertTrue(status.armed)
        XCTAssertEqual(status.shots, 3)
        XCTAssertTrue(status.canFire)
    }

    func testAStaleStatusIsWithheld() {
        // The whole point of this class.
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)

        XCTAssertNotNil(link.status(asOf: 12.0))
        XCTAssertNil(link.status(asOf: 13.0), "a status older than maxStatusAge must not be offered")
    }

    func testDisconnectingDropsTheStatusImmediately() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 10)
        XCTAssertNotNil(link.status(asOf: 10.1))

        transport.setConnected(false)
        XCTAssertNil(link.status(asOf: 10.2), "a dropped link cannot vouch for anything")
    }

    func testAMessageSplitAcrossTwoDeliveriesIsReassembled() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        let whole = healthyStatus() + Data("\n".utf8)
        transport.deliver(whole.prefix(20), at: 5)
        XCTAssertNil(link.status(asOf: 5.1))
        transport.deliver(whole.dropFirst(20), at: 5.2)

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
    }

    func testTwoMessagesInOneDeliveryBothArrive() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        let ack = Data("{\"ack\":\"park\",\"ok\":true}\n".utf8)
        transport.deliver(ack + healthyStatus() + Data("\n".utf8), at: 5)

        XCTAssertEqual(link.lastAck?.command, "park")
        XCTAssertNotNil(link.status(asOf: 5.1))
    }

    func testGarbageDoesNotDisturbTheLink() throws {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data("not json at all\n".utf8), at: 5)
        transport.deliver(Data("{\"unknown\":1}\n".utf8), at: 5.1)
        transport.deliver(healthyStatus() + Data("\n".utf8), at: 5.2)

        XCTAssertNotNil(try XCTUnwrap(link.status(asOf: 5.3)))
        XCTAssertEqual(link.malformedMessages, 2)
    }

    func testAnOverlongLineIsDiscardedRatherThanBuffered() {
        // A transport that never delivers a newline must not grow the buffer without bound.
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data(repeating: 0x41, count: 8192), at: 5)

        XCTAssertLessThanOrEqual(link.bufferedBytes, ActuatorLink.maxMessageBytes)
    }

    func testRefusalsAreCounted() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8), at: 5)
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"cooldown\"}\n".utf8), at: 6)
        transport.deliver(Data("{\"ack\":\"shoot\",\"ok\":false,\"why\":\"tank\"}\n".utf8), at: 7)

        XCTAssertEqual(link.refusals["cooldown"], 2)
        XCTAssertEqual(link.refusals["tank"], 1)
    }

    func testACommandThatCannotBeEncodedIsReportedNotSent() {
        let (link, transport) = makeLink()
        transport.isConnected = true
        XCTAssertThrowsError(try link.send(.aim(pan: .nan, tilt: 0)))
        XCTAssertTrue(transport.sentStrings.isEmpty)
    }

    func testFramingIsTheTransportsBusiness() throws {
        // The serial console reads one JSON object per line; BLE carries one object per
        // write and needs no terminator at all, with 180 bytes to spend. The link must not
        // decide this for both of them.
        let (link, transport) = makeLink()
        transport.isConnected = true
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[0], "{\"c\":\"park\"}")

        transport.framing = .newlineTerminated
        try link.send(.park)
        XCTAssertEqual(transport.sentStrings[1], "{\"c\":\"park\"}\n")
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter ActuatorLinkTests`
Expected: `error: cannot find 'FakeTransport' in scope`.

- [ ] **Step 3: Write the transport protocol**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Transport.swift`:

```swift
import Foundation

/// A pipe that carries bytes to the gnome and back. CoreBluetooth implements this on the
/// phone; the fake below implements it everywhere else.
/// How one message is marked off from the next on a particular pipe.
public enum Framing: Equatable, Sendable {
    /// One message per write, which is what a BLE characteristic gives for free.
    case perWrite
    /// One JSON object per line, which is what the firmware's serial console reads.
    case newlineTerminated

    public func frame(_ data: Data) -> Data {
        switch self {
        case .perWrite: return data
        case .newlineTerminated: return data + Data("\n".utf8)
        }
    }
}

public protocol Transport: AnyObject {
    var isConnected: Bool { get }
    var framing: Framing { get }
    /// Called with whatever arrived, in whatever sized pieces it arrived in.
    var onReceive: ((Data) -> Void)? { get set }
    /// Called when the link comes up or goes down.
    var onConnectionChange: ((Bool) -> Void)? { get set }
    func send(_ data: Data) throws
}

public enum TransportError: Error, Equatable {
    case notConnected
}

public final class FakeTransport: Transport {
    public var isConnected = false
    public var framing: Framing = .perWrite
    public var onReceive: ((Data) -> Void)?
    public var onConnectionChange: ((Bool) -> Void)?

    public private(set) var sent: [Data] = []
    public var sentStrings: [String] { sent.map { String(decoding: $0, as: UTF8.self) } }

    public init() {}

    public func send(_ data: Data) throws {
        guard isConnected else { throw TransportError.notConnected }
        sent.append(data)
    }

    /// Hand bytes to the link as if the radio had delivered them. `at` is the uptime the
    /// link should record them against.
    public func deliver<C: DataProtocol>(_ bytes: C, at uptime: TimeInterval) {
        receivedAt = uptime
        onReceive?(Data(bytes))
    }

    public func setConnected(_ connected: Bool) {
        isConnected = connected
        onConnectionChange?(connected)
    }

    /// Read by `ActuatorLink` in tests so a delivery can be given a timestamp without the
    /// production API growing one it does not need.
    public var receivedAt: TimeInterval = 0
}
```

- [ ] **Step 4: Write the link**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/ActuatorLink.swift`:

```swift
import Foundation
import DwarfCore

public struct LinkConfig: Equatable, Sendable {
    /// The firmware disarms after 3 s of silence. One beat a second leaves room for two to
    /// be lost before that matters.
    public var heartbeatInterval: TimeInterval = 1.0
    /// How old a status may be and still be offered to `FirePolicy`. The gnome publishes on
    /// change and at least once a second, so 2.5 s is two missed publications.
    public var maxStatusAge: TimeInterval = 2.5

    public init() {}
}

/// Everything about talking to the gnome except the radio.
///
/// The one rule worth stating out loud: `status(asOf:)` returns nil rather than something
/// old. `FirePolicy` checks `status.canFire` and has no idea when that status was true, so
/// a cached "armed, tank fine, no fault" handed back after the link died would keep
/// authorising shots. The firmware's own watchdog means they would be refused rather than
/// fired, but each refusal still spends an animal's budget on water it never received.
public final class ActuatorLink {
    /// Longest message the gnome ever sends, with room to spare. A transport that never
    /// produces a newline must not be able to grow this buffer forever.
    public static let maxMessageBytes = 1024

    public let config: LinkConfig
    private let transport: Transport

    private var buffer = Data()
    private var latestStatus: DeviceStatus?
    private var latestStatusAt: TimeInterval?
    private var lastHeartbeat: TimeInterval?

    public private(set) var lastAck: DeviceAck?
    public private(set) var refusals: [String: Int] = [:]
    public private(set) var malformedMessages = 0
    public var bufferedBytes: Int { buffer.count }
    public var isConnected: Bool { transport.isConnected }

    public init(transport: Transport, config: LinkConfig = LinkConfig()) {
        self.transport = transport
        self.config = config

        transport.onReceive = { [weak self] data in
            self?.absorb(data)
        }
        transport.onConnectionChange = { [weak self] connected in
            guard let self else { return }
            if !connected {
                // A link that has dropped cannot vouch for anything it said earlier.
                self.latestStatus = nil
                self.latestStatusAt = nil
                self.buffer.removeAll(keepingCapacity: true)
            }
            self.lastHeartbeat = nil
        }
    }

    /// Call once per cycle. Sends the heartbeat when one is due.
    public func tick(uptime: TimeInterval) {
        guard transport.isConnected else { return }
        if let last = lastHeartbeat, uptime - last < config.heartbeatInterval { return }
        lastHeartbeat = uptime
        try? send(.heartbeat)
    }

    /// The newest status, or nil when it is too old or the link is down.
    public func status(asOf uptime: TimeInterval) -> DeviceStatus? {
        guard transport.isConnected,
              let status = latestStatus,
              let at = latestStatusAt,
              uptime - at <= config.maxStatusAge else { return nil }
        return status
    }

    public func send(_ command: Command) throws {
        // Encoding first, so a command that cannot be represented never reaches the radio
        // and the caller hears about it rather than the gnome silently doing nothing.
        // Framing is the transport's: BLE carries one object per write, serial needs a
        // newline, and the link has no business knowing which it is talking to.
        try transport.send(transport.framing.frame(try command.encoded()))
    }

    private func absorb(_ data: Data) {
        buffer.append(data)

        while let newline = buffer.firstIndex(of: 0x0A) {
            let line = buffer[buffer.startIndex..<newline]
            buffer = buffer[buffer.index(after: newline)...]
            handle(Data(line))
        }

        if buffer.count > ActuatorLink.maxMessageBytes {
            // No terminator in a message this long means the stream is out of step. Keeping
            // the tail gives the next real message a chance to start cleanly.
            buffer = Data(buffer.suffix(ActuatorLink.maxMessageBytes))
            malformedMessages += 1
        }
    }

    private func handle(_ line: Data) {
        guard !line.isEmpty else { return }
        guard let message = try? IncomingMessage.decode(line) else {
            malformedMessages += 1
            return
        }

        switch message {
        case .status(let status):
            latestStatus = status
            latestStatusAt = receivedAt()
        case .ack(let ack):
            lastAck = ack
            if !ack.ok, let why = ack.why {
                refusals[why, default: 0] += 1
            }
        }
    }

    /// The uptime a delivery should be recorded against. The transport knows, because it is
    /// the thing being called back.
    private func receivedAt() -> TimeInterval {
        (transport as? FakeTransport)?.receivedAt ?? ProcessInfo.processInfo.systemUptime
    }
}
```

- [ ] **Step 5: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 42 tests, with 0 failures`.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): add the actuator link, and refuse to offer a stale status"
```

---

## Task 9: The radio (HARDWARE: the ESP32, after firmware Task 11)

**Files:**
- Create: `ios/DwarfApp/App/BluetoothTransport.swift`

CoreBluetooth behind the `Transport` protocol. Thin on purpose: everything worth testing is
already in `ActuatorLink`, and what is left here can only be exercised against a real radio.

**Blocked until firmware Task 11 lands** — there is no BLE server to connect to before that.
The serial console is the fallback for everything up to this point.

From the spec's section 7, and matching `firmware/src/main.cpp` exactly:

| | UUID |
|---|---|
| Service | `EC61AB6F-D20E-4217-93F9-4A3DF81B75D3` |
| `cmd`, write with response | `7C7FBA40-4383-4738-AD6B-09986229ED6A` |
| `status`, notify | `6DF54A5A-41DC-4414-AB6A-1354C959CF0A` |

This gnome's BLE address is `54:43:B2:44:2F:9E`. CoreBluetooth does not expose addresses —
it gives each peripheral an opaque per-app `identifier` — so the app discovers by service UUID,
then remembers the identifier of whatever it connected to. Advertised name is `dwarf`.

- [ ] **Step 1: Write the transport**

Create `ios/DwarfApp/App/BluetoothTransport.swift`:

```swift
import Foundation
import CoreBluetooth
import DwarfAdapters

/// The phone's side of the link.
///
/// Scans for the gnome's service, connects, subscribes to status notifications and writes
/// commands. Reconnection is automatic and quiet: a gnome that drops out for a moment
/// should not need anyone's attention, and `ActuatorLink` already refuses to offer a stale
/// status while it is away.
public final class BluetoothTransport: NSObject, Transport {
    public static let service = CBUUID(string: "EC61AB6F-D20E-4217-93F9-4A3DF81B75D3")
    public static let commandCharacteristic = CBUUID(string: "7C7FBA40-4383-4738-AD6B-09986229ED6A")
    public static let statusCharacteristic = CBUUID(string: "6DF54A5A-41DC-4414-AB6A-1354C959CF0A")

    /// One JSON object per write; the spec caps a message at 180 bytes.
    public let framing: Framing = .perWrite

    public private(set) var isConnected = false {
        didSet {
            guard isConnected != oldValue else { return }
            onConnectionChange?(isConnected)
        }
    }
    public var onReceive: ((Data) -> Void)?
    public var onConnectionChange: ((Bool) -> Void)?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var commandCharacteristic: CBCharacteristic?
    /// Remembered across launches so a reconnect does not need a fresh scan.
    private var knownIdentifier: UUID? {
        get { UserDefaults.standard.string(forKey: "gnome.peripheral").flatMap(UUID.init) }
        set { UserDefaults.standard.set(newValue?.uuidString, forKey: "gnome.peripheral") }
    }

    public override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .global(qos: .userInitiated))
    }

    public func send(_ data: Data) throws {
        guard isConnected, let peripheral, let characteristic = commandCharacteristic else {
            throw TransportError.notConnected
        }
        // With response, deliberately. Write-without-response is faster and silently drops
        // under congestion, and a dropped `park` leaves the head where it was.
        peripheral.writeValue(data, for: characteristic, type: .withResponse)
    }

    private func beginScanning() {
        guard central.state == .poweredOn else { return }
        if let identifier = knownIdentifier,
           let known = central.retrievePeripherals(withIdentifiers: [identifier]).first {
            connect(known)
            return
        }
        central.scanForPeripherals(withServices: [BluetoothTransport.service])
    }

    private func connect(_ peripheral: CBPeripheral) {
        self.peripheral = peripheral
        peripheral.delegate = self
        central.stopScan()
        central.connect(peripheral)
    }
}

extension BluetoothTransport: CBCentralManagerDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            beginScanning()
        } else {
            isConnected = false
        }
    }

    public func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                               advertisementData: [String: Any], rssi RSSI: NSNumber) {
        knownIdentifier = peripheral.identifier
        connect(peripheral)
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.discoverServices([BluetoothTransport.service])
    }

    public func centralManager(_ central: CBCentralManager,
                               didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        isConnected = false
        commandCharacteristic = nil
        beginScanning()
    }

    public func centralManager(_ central: CBCentralManager,
                               didFailToConnect peripheral: CBPeripheral, error: Error?) {
        isConnected = false
        beginScanning()
    }
}

extension BluetoothTransport: CBPeripheralDelegate {
    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard let service = peripheral.services?.first(where: { $0.uuid == BluetoothTransport.service })
        else { return }
        peripheral.discoverCharacteristics(
            [BluetoothTransport.commandCharacteristic, BluetoothTransport.statusCharacteristic],
            for: service)
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                           error: Error?) {
        for characteristic in service.characteristics ?? [] {
            switch characteristic.uuid {
            case BluetoothTransport.commandCharacteristic:
                commandCharacteristic = characteristic
            case BluetoothTransport.statusCharacteristic:
                peripheral.setNotifyValue(true, for: characteristic)
            default:
                break
            }
        }
        // Connected means "able to command", not "the radio linked". Until the command
        // characteristic exists, every send would throw anyway.
        isConnected = commandCharacteristic != nil
    }

    public func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard let value = characteristic.value else { return }
        onReceive?(value)
    }
}
```

- [ ] **Step 2: Build it**

```bash
cd ios/DwarfApp && xcodegen generate
xcodebuild -project DwarfApp.xcodeproj -scheme DwarfApp -sdk iphoneos -configuration Debug build CODE_SIGNING_ALLOWED=NO
```

Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 3: Prove it on hardware**

With the ESP32 powered and running the Task 11 firmware, and the app installed:

1. The app connects within a few seconds of launch and the status line stops saying "no link".
2. `nRF Connect` on another phone sees `dwarf` advertising the service UUID, and stops seeing
   a connectable advertisement once this app has connected.
3. Status notifications arrive at least once a second.
4. Pull the ESP32's power. The app reports no link within 3 s, and `status(asOf:)` returns
   nil — confirm the app does not keep showing the last known state as if it were current.
5. Restore power. The app reconnects on its own, without being restarted.
6. Walk the phone out of range and back. Same again.

Write down how long a reconnect takes. If it is more than a few seconds, the gnome spends
that time disarmed and the number matters for the field week.

- [ ] **Step 4: Commit**

```bash
git add ios/DwarfApp
git commit -m "feat(app): connect to the gnome over Bluetooth"
```

---

## Task 10: Power, heat and darkness

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/PowerManager.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/PowerManagerTests.swift`

Spec section 5.7. Three unrelated rules that all end in "do less": keep the phone's battery in
a band, back off when it gets hot, and stop looking when it gets dark.

`ProcessInfo.thermalState` exists on macOS, so that part tests honestly. Battery does not, so
it sits behind a protocol.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/PowerManagerTests.swift`:

```swift
import XCTest
@testable import DwarfAdapters

final class PowerManagerTests: XCTestCase {
    private func manager() -> (PowerManager, FakeBattery) {
        let battery = FakeBattery()
        return (PowerManager(battery: battery), battery)
    }

    func testTheChargerTurnsOnLowAndOffHigh() {
        let (power, battery) = manager()

        battery.level = 0.35
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 0).charger, true)

        battery.level = 0.60
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 1).charger, true,
                       "still charging between the thresholds")

        battery.level = 0.85
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 2).charger, false)

        battery.level = 0.60
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 3).charger, false,
                       "hysteresis: coming down from full, it stays off until 40%")
    }

    func testAnUnknownBatteryLevelChargesRatherThanGuesses() {
        // UIDevice reports -1 when monitoring is off or the reading is unavailable. A gnome
        // that stops charging because it cannot read its own battery is a gnome that dies
        // overnight.
        let (power, battery) = manager()
        battery.level = -1
        XCTAssertEqual(power.evaluate(thermal: .nominal, meanLuma: 120, uptime: 0).charger, true)
    }

    func testSeriousHeatHalvesTheRateAndStartsTheFan() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .serious, meanLuma: 120, uptime: 0)

        XCTAssertEqual(decision.cycleDivisor, 2)
        XCTAssertTrue(decision.fan)
        XCTAssertFalse(decision.pauseDetection)
    }

    func testCriticalHeatStopsEverything() {
        let (power, _) = manager()
        let decision = power.evaluate(thermal: .critical, meanLuma: 120, uptime: 0)

        XCTAssertTrue(decision.pauseDetection)
        XCTAssertTrue(decision.disarm)
        XCTAssertTrue(decision.fan)
    }

    func testDarknessPausesOnlyAfterItHasLasted() {
        // A cloud, or a cat walking over the lens, is not nightfall.
        let (power, _) = manager()

        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0).pauseDetection)
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 30).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)
    }

    func testLightHasToLastToUndoDarkness() {
        let (power, _) = manager()
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)

        // A car's headlights sweeping the garden must not restart detection.
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 62).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 100).pauseDetection)
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 123).pauseDetection)
    }

    func testAFlickerDoesNotResetTheDarknessTimer() {
        let (power, _) = manager()
        _ = power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 0)
        _ = power.evaluate(thermal: .nominal, meanLuma: 200, uptime: 30)
        // The light was brief, so darkness starts counting again from 30, not from 0.
        XCTAssertFalse(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 61).pauseDetection)
        XCTAssertTrue(power.evaluate(thermal: .nominal, meanLuma: 10, uptime: 91).pauseDetection)
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter PowerManagerTests`
Expected: `error: cannot find 'PowerManager' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/PowerManager.swift`:

```swift
import Foundation

/// The phone's battery, behind a protocol because `UIDevice` does not exist on a Mac.
public protocol BatteryReader: AnyObject {
    /// 0…1, or a negative number when the level is not available.
    var level: Float { get }
}

public final class FakeBattery: BatteryReader {
    public var level: Float = 0.5
    public init() {}
}

public struct PowerDecision: Equatable, Sendable {
    /// Whether the gnome should be charging the phone.
    public let charger: Bool
    public let fan: Bool
    /// Run one cycle in this many. 1 is full rate.
    public let cycleDivisor: Int
    public let pauseDetection: Bool
    /// Critical heat: stop asking for water at all, not merely stop looking.
    public let disarm: Bool
}

public struct PowerLimits: Equatable, Sendable {
    public var chargeBelow: Float = 0.40
    public var stopChargingAbove: Float = 0.80
    public var darkLuma: Double = 40
    /// How long darkness, or light, has to last before it is believed. A cloud is not
    /// nightfall and a car's headlights are not dawn.
    public var lightSettleTime: TimeInterval = 60

    public init() {}
}

/// Battery, heat and daylight. Three rules that all end in doing less.
public final class PowerManager {
    public var limits: PowerLimits
    private let battery: BatteryReader

    private var charging = true
    private var isDark = false
    /// When the luma last crossed the threshold in the direction it is currently heading.
    private var crossedAt: TimeInterval?

    public init(battery: BatteryReader, limits: PowerLimits = PowerLimits()) {
        self.battery = battery
        self.limits = limits
    }

    public func evaluate(thermal: ProcessInfo.ThermalState, meanLuma: Double,
                         uptime: TimeInterval) -> PowerDecision {
        PowerDecision(charger: shouldCharge(),
                      fan: thermal.rawValue >= ProcessInfo.ThermalState.serious.rawValue,
                      cycleDivisor: thermal == .serious ? 2 : 1,
                      pauseDetection: thermal == .critical || darkness(meanLuma, uptime),
                      disarm: thermal == .critical)
    }

    private func shouldCharge() -> Bool {
        let level = battery.level
        // A negative reading means the level is unavailable, not that it is empty. Charging
        // a full phone wastes a little heat; refusing to charge a flat one ends the night.
        guard level >= 0 else { return true }

        if charging, level >= limits.stopChargingAbove {
            charging = false
        } else if !charging, level <= limits.chargeBelow {
            charging = true
        }
        return charging
    }

    private func darkness(_ meanLuma: Double, _ uptime: TimeInterval) -> Bool {
        let looksDark = meanLuma.isFinite ? meanLuma < limits.darkLuma : true

        guard looksDark != isDark else {
            // Back on the side it was already on: whatever crossing was being timed is over.
            crossedAt = nil
            return isDark
        }

        guard let since = crossedAt else {
            crossedAt = uptime
            return isDark
        }

        if uptime - since >= limits.lightSettleTime {
            isDark = looksDark
            crossedAt = nil
        }
        return isDark
    }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 49 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): manage the battery, the heat and the light"
```

---

## Task 11: What survives a restart

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Store.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/StoreTests.swift`

Mode, calibration and masks on disk. `Calibration`, `MaskSet` and `Mode` are all already
`Codable` in `DwarfCore`, so this is mostly about failing well: a gnome that will not start
because one file got truncated during a power cut is worse than a gnome that starts
uncalibrated and says so.

The spec requires mode to persist across restarts. Note what that means: a gnome left in
`live` comes back in `live`.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/StoreTests.swift`:

```swift
import XCTest
import DwarfCore
@testable import DwarfAdapters

final class StoreTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testAFreshStoreIsUsableAndSaysItIsUncalibrated() {
        let store = Store(directory: directory)
        XCTAssertEqual(store.settings.mode, .dryRun, "a gnome that has never been told otherwise does not fire")
        XCTAssertTrue(store.calibration.points.isEmpty)
        XCTAssertFalse(store.isCalibrated)
    }

    func testSettingsSurviveARestart() throws {
        let store = Store(directory: directory)
        store.settings.mode = .live
        store.settings.quarterTurns = 1
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .live)
        XCTAssertEqual(reopened.settings.quarterTurns, 1)
    }

    func testACalibrationSurvivesARestart() throws {
        let store = Store(directory: directory)
        store.calibration = Calibration(
            points: (0..<6).map {
                CalibrationPoint(image: Point(x: 0.1 * Double($0), y: 0.6),
                                 pan: Double($0), tilt: 1, rangeM: 4)
            },
            heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4)])
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.calibration.points.count, 6)
        XCTAssertTrue(reopened.isCalibrated)
    }

    func testATruncatedFileFallsBackRatherThanRefusingToStart() throws {
        // A power cut during a write is the normal way this happens, and a gnome that will
        // not boot in the garden is worse than one that boots uncalibrated and says so.
        let store = Store(directory: directory)
        store.settings.mode = .live
        try store.save()

        try Data("{ \"mode\": ".utf8).write(to: directory.appendingPathComponent("settings.json"))

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .dryRun)
        XCTAssertEqual(reopened.loadFailures, ["settings.json"])
    }

    func testAWriteIsAtomic() throws {
        // Written to a neighbouring file and moved into place, so the file at the real path
        // is always either the old one or the new one and never half of either.
        let store = Store(directory: directory)
        store.settings.mode = .live
        try store.save()
        try store.save()

        let leftovers = try FileManager.default.contentsOfDirectory(atPath: directory.path)
            .filter { $0.hasSuffix(".tmp") }
        XCTAssertTrue(leftovers.isEmpty, "temporary files left behind: \(leftovers)")
    }

    func testMasksRoundTrip() throws {
        let store = Store(directory: directory)
        store.masks = MaskSet(
            ignoreZones: [Polygon(points: [Point(x: 0, y: 0), Point(x: 0.2, y: 0), Point(x: 0.2, y: 0.2)])],
            noFireZones: [Polygon(points: [Point(x: 0.8, y: 0.8), Point(x: 1, y: 0.8), Point(x: 1, y: 1)])])
        try store.save()

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.masks.ignoreZones.count, 1)
        XCTAssertEqual(reopened.masks.noFireZones.count, 1)
        XCTAssertEqual(reopened.masks.noFireMargin, 0.005, accuracy: 1e-12,
                       "the safety margin must survive a round trip too")
    }

    func testAFormatFromTheFutureIsNotGuessedAt() throws {
        // A phone running an old build against files written by a new one should say so
        // rather than misread them.
        let store = Store(directory: directory)
        try store.save()
        let path = directory.appendingPathComponent("settings.json")
        var object = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
        object["formatVersion"] = DwarfAdapters.formatVersion + 1
        try JSONSerialization.data(withJSONObject: object).write(to: path)

        let reopened = Store(directory: directory)
        XCTAssertEqual(reopened.settings.mode, .dryRun)
        XCTAssertEqual(reopened.loadFailures, ["settings.json"])
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter StoreTests`
Expected: `error: cannot find 'Store' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Store.swift`:

```swift
import Foundation
import DwarfCore

/// Everything the owner can change that is not a calibration or a mask.
public struct Settings: Codable, Equatable, Sendable {
    public var formatVersion = DwarfAdapters.formatVersion
    /// Persisted across restarts, as the spec requires. A gnome left in `live` comes back
    /// in `live`.
    public var mode: Mode = .dryRun
    /// Quarter turns clockwise to stand the camera buffer upright; see `FrameGeometry`.
    public var quarterTurns = 0
    /// The model's input side. M0 decides this.
    public var modelSide = 640
    public var minConfidence = 0.25

    public init() {}
}

/// Mode, calibration and masks on disk.
///
/// Reading is forgiving and writing is atomic. A file that will not parse is reported and
/// replaced with a default, because a gnome that refuses to start in the garden is worse
/// than one that starts uncalibrated and says so on its screen — and an uncalibrated gnome
/// cannot fire at all, so failing this way is safe as well as convenient.
public final class Store {
    public var settings: Settings
    public var calibration: Calibration
    public var masks: MaskSet

    /// Files that could not be read this launch, for the status screen.
    public private(set) var loadFailures: [String] = []

    /// True when there is enough calibration for `Aimer` to fit at all. Below this the
    /// gnome tracks and shows a live view but has no route to a shot.
    public var isCalibrated: Bool { calibration.points.count >= 6 }

    private let directory: URL

    public init(directory: URL) {
        self.directory = directory

        var failures: [String] = []
        func load<T: Decodable>(_ name: String, _ fallback: T) -> T {
            let url = directory.appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath: url.path) else { return fallback }
            do {
                return try JSONDecoder().decode(T.self, from: Data(contentsOf: url))
            } catch {
                failures.append(name)
                return fallback
            }
        }

        var loaded: Settings = load("settings.json", Settings())
        if loaded.formatVersion > DwarfAdapters.formatVersion {
            // Written by a newer build. Guessing at fields this one does not understand is
            // how a setting silently reverts.
            failures.append("settings.json")
            loaded = Settings()
        }
        self.settings = loaded
        self.calibration = load("calibration.json", .empty)
        self.masks = load("masks.json", .empty)
        self.loadFailures = failures
    }

    public func save() throws {
        settings.formatVersion = DwarfAdapters.formatVersion
        try write(settings, to: "settings.json")
        try write(calibration, to: "calibration.json")
        try write(masks, to: "masks.json")
    }

    /// Written beside the real file and moved into place, so a power cut mid-write leaves
    /// the previous version rather than half of the new one.
    private func write<T: Encodable>(_ value: T, to name: String) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(value)

        let target = directory.appendingPathComponent(name)
        let temporary = directory.appendingPathComponent(name + ".tmp")
        try data.write(to: temporary, options: .atomic)
        _ = try FileManager.default.replaceItemAt(target, withItemAt: temporary)
    }
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 56 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): persist mode, calibration and masks"
```

---

## Task 12: The runtime

**Files:**
- Create: `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Runtime.swift`
- Test: `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/RuntimeTests.swift`

The only thing that knows about all the pieces at once. It owns the `Cycle`, feeds it, and
carries out what it decides.

**This is the task that honours `DwarfCore`'s contract**, and most of its tests exist because
of a specific bullet in that README. Read it again before starting. In particular: detection
is asynchronous, so a cycle that has had no answer must pass `.pending` and not an empty
answer, and an answer must be timestamped with when its *frame* was captured.

- [ ] **Step 1: Write the failing tests**

Create `ios/DwarfApp/DwarfAdapters/Tests/DwarfAdaptersTests/RuntimeTests.swift`:

```swift
import XCTest
import CoreVideo
import DwarfCore
@testable import DwarfAdapters

final class RuntimeTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    private struct Rig {
        let runtime: Runtime
        let detector: FakeDetector
        let transport: FakeTransport
        let link: ActuatorLink
        let clock: TestClock
        let battery: FakeBattery
        let store: Store
    }

    /// A calibration dense enough for the Aimer to fit, covering the lower half of the
    /// frame where the ground is.
    private func calibration() -> Calibration {
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                points.append(CalibrationPoint(image: Point(x: x, y: y),
                                               pan: (x - 0.5) * 100,
                                               tilt: 30 - 34 * y,
                                               rangeM: 8 - 6 * y))
            }
        }
        return Calibration(points: points,
                           heightOffsets: [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4),
                                           HeightOffsetSample(rangeM: 6, deltaTiltDeg: 2)])
    }

    private func makeRig(mode: Mode = .live) throws -> Rig {
        let store = Store(directory: directory)
        store.settings.mode = mode
        store.calibration = calibration()

        let clock = TestClock()
        // Noon in June, inside the active window.
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15; components.hour = 12
        clock.now = Calendar.current.date(from: components)!

        let transport = FakeTransport()
        transport.isConnected = true
        // One clock for the whole rig. The link stamps arriving statuses with it and the
        // runtime asks about uptimes from it; two clocks is exactly the defect the review
        // of Task 8 found, where a single rewind withheld every status forever.
        let steady = SteadyClock(wrapping: clock)
        let link = ActuatorLink(transport: transport, clock: steady)
        let detector = FakeDetector()
        let battery = FakeBattery()

        let runtime = Runtime(
            store: store,
            link: link,
            detector: detector,
            geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080), quarterTurns: 0),
            power: PowerManager(battery: battery),
            clock: steady)

        return Rig(runtime: runtime, detector: detector, transport: transport, link: link,
                   clock: clock, battery: battery, store: store)
    }

    private func brightBuffer() -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(kCFAllocatorDefault, 1920, 1080,
                            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &buffer)
        let pixels = buffer!
        CVPixelBufferLockBaseAddress(pixels, [])
        let y = CVPixelBufferGetBaseAddressOfPlane(pixels, 0)!
        for row in 0..<1080 {
            memset(y.advanced(by: row * CVPixelBufferGetBytesPerRowOfPlane(pixels, 0)), 120, 1920)
        }
        let uv = CVPixelBufferGetBaseAddressOfPlane(pixels, 1)!
        for row in 0..<540 {
            memset(uv.advanced(by: row * CVPixelBufferGetBytesPerRowOfPlane(pixels, 1)), 128, 1920)
        }
        CVPixelBufferUnlockBaseAddress(pixels, [])
        return pixels
    }

    /// The link timestamps this from the clock, so the caller sets `rig.clock.uptime`
    /// first, exactly as the real transport's callback would arrive mid-cycle.
    private func healthyStatus(in rig: Rig) {
        rig.transport.deliver(Data("""
        {"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":true,"charge":false,\
        "fan":false,"temp":22,"fault":null,"shots":0}\n
        """.utf8))
    }

    func testACycleWithNoAnswerYetIsPendingNotAnEmptyAnswer() throws {
        // The contract bullet that, when broken, leaves the whole system green and inert.
        let rig = try makeRig()
        rig.detector.next = []

        rig.clock.uptime = 0
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertEqual(rig.runtime.lastReportWasPending, true,
                       "no detector answer had come back, so the tracker must not be told the detector looked")
    }

    func testAnAnswerIsTimestampedWithItsFrameNotItsArrival() throws {
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.6, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        rig.clock.uptime = 10
        rig.runtime.handle(frame: brightBuffer())   // asks
        rig.runtime.waitForDetector()
        rig.clock.uptime = 10.4
        rig.runtime.handle(frame: brightBuffer())   // collects

        XCTAssertEqual(rig.runtime.lastAnswerCapturedAt, 10, accuracy: 1e-9,
                       "the box came from the frame captured at 10, not from the one at 10.4")
    }

    func testAnIntermittentDetectorStillGetsAShotOff() throws {
        // End to end, through every real component except the radio and the model: a
        // motionless cat, a detector that answers roughly every third cycle, and a shot.
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        let shots = rig.transport.sentStrings.filter { $0.contains("\"shoot\"") }
        XCTAssertFalse(shots.isEmpty, "expected at least one shoot: \(Set(rig.transport.sentStrings))")
    }

    func testADryRunNeverReachesTheNozzle() throws {
        let rig = try makeRig(mode: .dryRun)
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        XCTAssertTrue(rig.transport.sentStrings.allSatisfy { !$0.contains("\"shoot\"") },
                      "a dry run that fires is worse than no dry run at all")
        XCTAssertGreaterThan(rig.runtime.wouldShootCount, 0, "but it must still record what it would have done")
    }

    func testNoShotWithoutAFreshStatus() throws {
        // The status is never delivered, so FirePolicy is handed nil every cycle.
        let rig = try makeRig()
        rig.detector.next = [RawBox(box: Rect(x: 0.45, y: 0.62, width: 0.08, height: 0.06),
                                    confidence: 0.9)]

        for i in 0..<120 {
            rig.clock.uptime = Double(i) * 0.1
            rig.runtime.handle(frame: brightBuffer())
            if i % 3 == 0 { rig.runtime.waitForDetector() }
        }

        XCTAssertTrue(rig.transport.sentStrings.allSatisfy { !$0.contains("\"shoot\"") })
    }

    func testCriticalHeatDisarmsAndStopsLooking() throws {
        let rig = try makeRig()
        rig.runtime.thermalOverride = .critical
        rig.clock.uptime = 1
        healthyStatus(in: rig)
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertTrue(rig.transport.sentStrings.contains { $0.contains("\"arm\"") && $0.contains("false") })
        XCTAssertEqual(rig.detector.calls, 0, "nothing should be asked of the model while it is this hot")
    }

    func testTheDisarmIsSentOnceNotAtFrameRate() throws {
        let rig = try makeRig()
        rig.runtime.thermalOverride = .critical

        for i in 0..<30 {
            rig.clock.uptime = Double(i) * 0.1
            healthyStatus(in: rig)
            rig.runtime.handle(frame: brightBuffer())
        }

        let disarms = rig.transport.sentStrings.filter { $0.contains("\"arm\"") }
        XCTAssertEqual(disarms.count, 1, "the firmware latches it; repeating is noise: \(disarms.count)")
    }

    func testTheSchedulerIsToldTheRealFrameSize() throws {
        // A contract bullet: crop rectangles are fractions of a frame whose size only the
        // app knows.
        let rig = try makeRig()
        XCTAssertEqual(rig.runtime.schedulerConfig.frameWidthPixels, 1920)
        XCTAssertEqual(rig.runtime.schedulerConfig.frameHeightPixels, 1080)
    }

    func testAFailingDetectorDoesNotStopTheLoop() throws {
        struct Broken: Error {}
        let rig = try makeRig()
        rig.detector.error = Broken()

        rig.clock.uptime = 1
        rig.runtime.handle(frame: brightBuffer())
        rig.runtime.waitForDetector()
        rig.clock.uptime = 1.2
        rig.runtime.handle(frame: brightBuffer())

        XCTAssertGreaterThan(rig.runtime.detectorFailures, 0)
        XCTAssertEqual(rig.runtime.lastReportWasPending, true, "a failed inference is not evidence of absence")
    }
}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test --filter RuntimeTests`
Expected: `error: cannot find 'Runtime' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfApp/DwarfAdapters/Sources/DwarfAdapters/Runtime.swift`:

```swift
import Foundation
import CoreVideo
import DwarfCore

/// The loop. Owns the `Cycle` and is the only thing that knows about every adapter at once.
///
/// Most of what follows is `ios/DwarfCore/README.md`'s "contract this package cannot
/// enforce", made into code. The two that matter most:
///
/// - Detection is asynchronous. A cycle with no answer back yet reports `.pending`, never an
///   empty answer, because an empty answer means "the detector looked and saw nothing" and
///   counts against confirmation. Report those and a perfectly detected cat never confirms.
/// - An answer is timestamped with when its **frame** was captured, not when it came back.
///   Stillness gates firing, and a late answer at the current time makes a moving animal
///   look stiller than it is.
public final class Runtime {
    private let store: Store
    private let link: ActuatorLink
    private let detector: Detector
    private let converter: FrameConverter
    private let power: PowerManager
    private let clock: Clock
    private let cycle: Cycle

    private let detectorQueue = DispatchQueue(label: "garden.dwarf.detector")
    private var detectorBusy = false
    /// An answer that has come back and has not been handed to the tracker yet.
    private var pendingAnswer: (detections: [Detection], capturedAt: TimeInterval)?
    private let lock = NSLock()

    private var cycleCounter = 0

    public private(set) var schedulerConfig = SchedulerConfig()
    public private(set) var lastReportWasPending = true
    public private(set) var lastAnswerCapturedAt: TimeInterval?
    public private(set) var wouldShootCount = 0
    public private(set) var detectorFailures = 0
    public private(set) var lastOutput: CycleOutput?
    /// Set in tests; production reads `ProcessInfo`.
    public var thermalOverride: ProcessInfo.ThermalState?

    public init(store: Store, link: ActuatorLink, detector: Detector, geometry: FrameGeometry,
                power: PowerManager, clock: Clock) {
        self.store = store
        self.link = link
        self.detector = detector
        self.power = power
        self.clock = clock
        self.converter = FrameConverter(geometry: geometry)

        // The one place SchedulerConfig learns how big the frame really is. A remembered
        // constant here means crops cut from the wrong part of the garden.
        var config = SchedulerConfig()
        config.cropPixels = store.settings.modelSide
        geometry.apply(to: &config)
        self.schedulerConfig = config

        self.cycle = Cycle(calibration: store.calibration, schedulerConfig: config)
        self.cycle.masks = store.masks
        self.cycle.mode = store.settings.mode
    }

    /// Call once per camera frame, on the capture queue.
    public func handle(frame pixelBuffer: CVPixelBuffer) {
        let uptime = clock.uptime
        link.tick(uptime: uptime)

        guard let gray = converter.gray(from: pixelBuffer) else { return }

        let thermal = thermalOverride ?? ProcessInfo.processInfo.thermalState
        let decision = power.evaluate(thermal: thermal, meanLuma: gray.meanLuma, uptime: uptime)
        apply(decision, at: uptime)

        if decision.pauseDetection { return }
        cycleCounter += 1
        if decision.cycleDivisor > 1, cycleCounter % decision.cycleDivisor != 0 { return }

        let report = collectAnswer()
        lastReportWasPending = { if case .pending = report { return true } else { return false } }()

        let output = cycle.process(frame: gray,
                                   detector: report,
                                   status: link.status(asOf: uptime),
                                   now: clock.now,
                                   uptime: uptime)
        lastOutput = output
        carryOut(output.decision)
        askDetector(about: output.cropRequests, from: pixelBuffer, capturedAt: uptime)
    }

    /// Replaces the calibration after the owner records a point.
    public func update(calibration: Calibration) {
        store.calibration = calibration
        cycle.update(calibration: calibration)
    }

    public func update(mode: Mode) {
        store.settings.mode = mode
        cycle.mode = mode
    }

    // MARK: detection

    private func collectAnswer() -> DetectorReport {
        lock.lock()
        defer { lock.unlock() }
        guard let answer = pendingAnswer else { return .pending }
        pendingAnswer = nil
        lastAnswerCapturedAt = answer.capturedAt
        return .answer(answer.detections, capturedAt: answer.capturedAt)
    }

    private func askDetector(about requests: [CropRequest], from pixelBuffer: CVPixelBuffer,
                             capturedAt: TimeInterval) {
        guard !requests.isEmpty else { return }
        lock.lock()
        let busy = detectorBusy
        if !busy { detectorBusy = true }
        lock.unlock()
        guard !busy else { return }

        // The inputs are cut on this queue, while the buffer is still guaranteed valid. The
        // capture system reuses its buffers, and a CVPixelBuffer held past the delegate call
        // is a buffer whose contents change underneath the model.
        let side = store.settings.modelSide
        let inputs: [(CVPixelBuffer, PixelRect)] = requests.compactMap { request in
            guard let rect = converter.geometry.validPixelRect(of: request.rect),
                  let input = converter.modelInput(from: pixelBuffer, cropInFrame: rect, side: side)
            else { return nil }
            return (input, rect)
        }
        guard !inputs.isEmpty else {
            lock.lock(); detectorBusy = false; lock.unlock()
            return
        }

        detectorQueue.async { [weak self] in
            guard let self else { return }
            var detections: [Detection] = []
            var failed = false

            for (input, rect) in inputs {
                do {
                    let boxes = try self.detector.detect(input: input)
                    let letterbox = Letterbox(crop: rect, side: side)
                    for box in boxes {
                        let frameBox = letterbox.frameBox(fromModel: box.box, crop: rect,
                                                          frame: self.converter.geometry.frame)
                        detections.append(Detection(box: frameBox, confidence: box.confidence))
                    }
                } catch {
                    failed = true
                }
            }

            self.lock.lock()
            if failed {
                self.detectorFailures += 1
            }
            // A failed inference is not evidence of absence, so nothing is handed over and
            // the next cycle reports pending.
            if !failed {
                self.pendingAnswer = (detections, capturedAt)
            }
            self.detectorBusy = false
            self.lock.unlock()
        }
    }

    /// Blocks until the detector queue has drained. Tests only.
    public func waitForDetector() {
        detectorQueue.sync {}
    }

    // MARK: acting

    private func carryOut(_ decision: FireDecision) {
        switch decision {
        case .none:
            break
        case .aim(let pan, let tilt):
            try? link.send(.aim(pan: pan, tilt: tilt))
        case .park:
            try? link.send(.park)
        case .shoot(let pan, let tilt, let ms):
            // The only place in the app allowed to turn a decision into water.
            try? link.send(.shoot(pan: pan, tilt: tilt, ms: ms))
        case .wouldShoot:
            // Deliberately not sent. A dry run that fires is worse than no dry run.
            wouldShootCount += 1
        }
    }

    private func apply(_ decision: PowerDecision, at uptime: TimeInterval) {
        // Once, on the way into critical, not ten times a second for as long as it lasts.
        // The gnome stays disarmed because the firmware latches it, and a command repeated
        // at frame rate is a radio kept busy for nothing while the phone is already too hot.
        if decision.disarm != lastDisarm {
            lastDisarm = decision.disarm
            if decision.disarm { try? link.send(.arm(false)) }
        }
        if decision.charger != lastCharger {
            lastCharger = decision.charger
            try? link.send(.charge(decision.charger))
        }
        if decision.fan != lastFan {
            lastFan = decision.fan
            try? link.send(.fan(decision.fan))
        }
    }

    private var lastCharger: Bool?
    private var lastFan: Bool?
    private var lastDisarm: Bool?
}
```

- [ ] **Step 4: Run the tests**

Run: `cd ios/DwarfApp/DwarfAdapters && swift test`
Expected: `Executed 65 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfApp/DwarfAdapters
git commit -m "feat(app): wire the runtime together and honour DwarfCore's contract"
```

---

## Task 13: The camera and the screen

**Files:**
- Create: `ios/DwarfApp/App/CameraSource.swift`
- Create: `ios/DwarfApp/App/BatteryReader.swift`
- Create: `ios/DwarfApp/App/GnomeController.swift`
- Modify: `ios/DwarfApp/App/RootView.swift`
- Modify: `ios/DwarfApp/App/DwarfAppMain.swift`

The iOS-only shell: a capture session, the battery, and a screen that shows what the runtime
is thinking. Deliberately last and deliberately thin — by this point everything that can be
wrong has a test somewhere else.

The screen matters more than it looks. Until the second plan builds the web UI, it is the
only way to see whether the gnome is working.

- [ ] **Step 1: Write the camera**

Create `ios/DwarfApp/App/CameraSource.swift`:

```swift
import Foundation
import AVFoundation
import CoreVideo

/// 1080p frames at roughly 10 fps, in the camera's native format.
///
/// `420YpCbCr8BiPlanarFullRange` is what the sensor produces, so nothing is converted at
/// capture time and `FrameConverter` gets the luma plane for free. 1080p rather than 4K:
/// at 6 m a cat is about 75 px long here, which is enough, and four times the pixels would
/// cost four times the heat for no more reach.
public final class CameraSource: NSObject {
    public var onFrame: ((CVPixelBuffer) -> Void)?

    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "garden.dwarf.capture")

    public func start() throws {
        session.beginConfiguration()
        session.sessionPreset = .hd1920x1080

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            throw CameraError.noCamera
        }
        session.addInput(input)

        output.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String:
                kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
        ]
        // Frames are dropped rather than queued. A backlog would hand the runtime pictures
        // of where the cat used to be.
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(output) else { throw CameraError.noCamera }
        session.addOutput(output)

        try device.lockForConfiguration()
        // Ask for 10 fps at both ends, so the sensor is not working harder than the pipeline
        // can consume. On an A9 every unused frame is heat.
        device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 10)
        device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 10)
        // The gnome does not move and the garden does not change distance. Continuous
        // autofocus hunting through a plastic window is worse than a fixed far focus.
        if device.isFocusModeSupported(.continuousAutoFocus) {
            device.focusMode = .continuousAutoFocus
        }
        device.unlockForConfiguration()

        session.commitConfiguration()
        session.startRunning()
    }

    public func stop() {
        session.stopRunning()
    }

    public enum CameraError: Error { case noCamera }
}

extension CameraSource: AVCaptureVideoDataOutputSampleBufferDelegate {
    public func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                              from connection: AVCaptureConnection) {
        guard let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        onFrame?(buffer)
    }
}
```

- [ ] **Step 2: Write the battery reader**

Create `ios/DwarfApp/App/BatteryReader.swift`:

```swift
import UIKit
import DwarfAdapters

/// `UIDevice` behind the protocol `PowerManager` expects.
public final class DeviceBattery: BatteryReader {
    public init() {
        UIDevice.current.isBatteryMonitoringEnabled = true
    }

    /// -1 when the level is not available, which `PowerManager` reads as "charge anyway".
    public var level: Float { UIDevice.current.batteryLevel }
}
```

- [ ] **Step 3: Write the controller that holds it all**

Create `ios/DwarfApp/App/GnomeController.swift`:

```swift
import Foundation
import SwiftUI
import DwarfCore
import DwarfAdapters

/// Assembles the gnome and publishes enough of it for the screen.
///
/// Deliberately **not** `@MainActor`: camera frames arrive on the capture queue and go
/// straight into the runtime from there, so isolating this type to the main actor would
/// either block the UI or need every frame to hop threads. Only the published properties
/// touch the main actor, and they do it explicitly.
final class GnomeController: ObservableObject {
    @Published private(set) var line = "starting"
    @Published private(set) var trackCount = 0
    @Published private(set) var linkUp = false
    @Published private(set) var mode: Mode = .dryRun
    /// True when the model could not be loaded. The gnome then tracks nothing at all, and
    /// silently looking like it works is the worst way for that to present.
    @Published private(set) var modelMissing = false

    private let camera = CameraSource()
    private let runtime: Runtime
    private let store: Store
    private let link: ActuatorLink

    init() {
        let directory = FileManager.default.urls(for: .applicationSupportDirectory,
                                                 in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let store = Store(directory: directory)
        let clock = SteadyClock(wrapping: SystemClock())
        let transport = BluetoothTransport()
        let link = ActuatorLink(transport: transport, clock: clock)
        // A missing or unreadable model must be visible, not papered over: the fallback
        // detector never finds anything, so the gnome would sit there looking healthy and
        // watching nothing.
        let detector: Detector
        var missing = false
        if let model = try? CoreMLDetector(minConfidence: store.settings.minConfidence) {
            detector = model
        } else {
            detector = FakeDetector()
            missing = true
        }

        self.store = store
        self.link = link
        self.runtime = Runtime(
            store: store,
            link: link,
            detector: detector,
            geometry: FrameGeometry(buffer: PixelSize(width: 1920, height: 1080),
                                    quarterTurns: store.settings.quarterTurns),
            power: PowerManager(battery: DeviceBattery()),
            clock: clock)
        self.mode = store.settings.mode
        self.modelMissing = missing
    }

    func start() {
        camera.onFrame = { [weak self] buffer in
            guard let self else { return }
            self.runtime.handle(frame: buffer)
            Task { @MainActor in self.refresh() }
        }
        do {
            try camera.start()
            line = "watching"
        } catch {
            line = "no camera: \(error)"
        }
    }

    func set(mode: Mode) {
        self.mode = mode
        runtime.update(mode: mode)
        try? store.save()
    }

    private func refresh() {
        linkUp = link.isConnected
        trackCount = runtime.lastOutput?.tracks.count ?? 0

        if modelMissing {
            line = "MODEL MISSING — nothing is being detected"
        } else if !store.loadFailures.isEmpty {
            line = "unreadable: \(store.loadFailures.joined(separator: ", "))"
        } else if !store.isCalibrated {
            line = "tracking only — not calibrated"
        } else if let decision = runtime.lastOutput?.decision {
            line = describe(decision)
        }
    }

    private func describe(_ decision: FireDecision) -> String {
        switch decision {
        case .none: return "watching"
        case .aim(let pan, let tilt): return String(format: "aim %.1f° %.1f°", pan, tilt)
        case .park: return "parked"
        case .shoot(_, _, let ms): return "SHOT \(ms) ms"
        case .wouldShoot(_, _, let ms): return "would shoot \(ms) ms"
        }
    }
}
```

- [ ] **Step 4: Write the screen**

Replace `ios/DwarfApp/App/RootView.swift`:

```swift
import SwiftUI
import DwarfCore

struct RootView: View {
    @StateObject private var gnome = GnomeController()

    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 8) {
                Circle()
                    .fill(gnome.linkUp ? Color.green : Color.red)
                    .frame(width: 10, height: 10)
                Text(gnome.linkUp ? "gnome connected" : "no link")
                    .font(.footnote)
            }

            Text(gnome.line)
                .font(.system(.title2, design: .monospaced))
                .multilineTextAlignment(.center)

            Text("\(gnome.trackCount) track\(gnome.trackCount == 1 ? "" : "s")")
                .font(.footnote).foregroundStyle(.secondary)

            Picker("mode", selection: Binding(get: { gnome.mode },
                                              set: { gnome.set(mode: $0) })) {
                Text("disarmed").tag(Mode.disarmed)
                Text("dry-run").tag(Mode.dryRun)
                Text("live").tag(Mode.live)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
        .foregroundStyle(.white)
        .onAppear { gnome.start() }
    }
}
```

- [ ] **Step 5: Ask for the camera at launch**

In `ios/DwarfApp/App/DwarfAppMain.swift`, add above `WindowGroup`'s content, inside `init`:

```swift
        AVCaptureDevice.requestAccess(for: .video) { _ in }
```

and `import AVFoundation` at the top.

- [ ] **Step 6: Build**

```bash
cd ios/DwarfApp && xcodegen generate
xcodebuild -project DwarfApp.xcodeproj -scheme DwarfApp -sdk iphoneos -configuration Release build CODE_SIGNING_ALLOWED=NO
```

Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 7: Commit**

```bash
git add ios/DwarfApp
git commit -m "feat(app): add the camera, the battery and the status screen"
```

---

## Task 14: Dry-run on the bench (HARDWARE: phone and ESP32)

**Files:**
- Create: `hardware/dry-run-checklist.md`

The gnome, assembled loosely on a bench, watching a room, in dry-run, with the pump off and
the tank empty. This is the milestone the whole plan exists to reach: everything connected,
nothing wet.

**Prerequisites:** firmware Tasks 10–12 done, the wiring in `hardware/wiring.md` built
including the gate pull-downs and flyback diodes, and the M0 number from Task 6.

- [ ] **Step 1: Write the checklist**

Create `hardware/dry-run-checklist.md`:

```markdown
# Dry-run checklist

Pump unplugged, tank empty, valve connected so its click can be heard. Mode `dry-run`
throughout — the app must never reach `live` during this.

## Before power

- [ ] Gate pull-downs fitted on GPIO 25, 26, 27, 14
- [ ] Flyback diodes across the solenoid and the pump, banded end to +12 V
- [ ] Both buck converters confirmed at 6.0 V and 5.0 V off-load
- [ ] Star ground
- [ ] Pump disconnected at its connector, not merely switched off in software

## Link

- [ ] App reports "gnome connected" within 10 s of launch
- [ ] Status notifications at least once a second
- [ ] Pull the ESP32's power: app reports no link within 3 s
- [ ] Restore power: reconnects unaided, note how long it takes
- [ ] Unplug the temperature probe while armed: gnome reports TEMP_SENSOR and disarms

## Seeing

- [ ] Phone mounted the way it will be in the gnome, with the quarter turns set to match
- [ ] Walk in front of the camera: track count rises
- [ ] Stand still: the screen reaches "would shoot"
- [ ] The head turns towards you and follows as you move slowly
- [ ] Walk out of shot: the head parks after about 10 s
- [ ] Hold a printed photograph of a cat at 3 m: it is detected

## Refusing

Each of these must end in no "would shoot", and the screen should say why:

- [ ] Closer than 2 m
- [ ] Standing in a no-fire zone, once one is written into masks.json
- [ ] Moving continuously
- [ ] Lights off — after 60 s it stops looking altogether
- [ ] Mode set to `disarmed`

## Heat

- [ ] Thirty minutes of continuous dry-run. Note the thermal state and whether the fan came on
- [ ] The phone stays below 35 °C ambient at the sled

## The valve

- [ ] Throughout all of the above, the valve never clicks
- [ ] Power-cycle the ESP32 with everything connected: still no click
```

- [ ] **Step 2: Run it**

Work through the checklist. Anything that fails is a finding, not a task to skip.

- [ ] **Step 3: Record what happened**

Fill in the boxes, write the observed numbers into the document — reconnect time, thermal
state, detection range on a printed cat — and commit it. Those numbers are the baseline the
field week is judged against.

- [ ] **Step 4: Commit**

```bash
git add hardware/dry-run-checklist.md
git commit -m "Record the bench dry-run results"
```

---

## Definition of done

- `cd ios/DwarfApp/DwarfAdapters && swift test` passes, around 65 tests.
- `cd ios/DwarfCore && swift test` still passes, 162 tests.
- `xcodebuild -sdk iphoneos ... CODE_SIGNING_ALLOWED=NO` builds the app in Release.
- `grep -rn "import UIKit" ios/DwarfApp/DwarfAdapters/Sources` returns nothing.
- `grep -rn "Date()" ios/DwarfApp/DwarfAdapters/Sources` returns nothing outside `Clock.swift`.
- The M0 number is written into this plan, and `Settings.modelSide` matches it.
- The dry-run checklist is filled in and committed.

## What this plan deliberately leaves out

- **The web UI, the event store, calibration and mask editors.** The second plan. Until then
  calibration and masks are files, and the phone's own screen is the only view.
- **Ack feedback into `FirePolicy`.** Nothing consumes `DeviceAck` beyond counting refusals,
  so a shot the firmware bounces still spends the animal's budget. `minDeviceInterval`
  removes the common cause. Proper handling needs the event store to log against.
- **Background operation.** The camera requires the foreground. Guided Access pins the app.
- **Recovering from a phone reboot without a computer.** Out of scope in the spec, and still is.
- **A replay harness.** The spec asks for one that runs recorded clips through the whole
  pipeline. It needs recorded clips, which need the event store, which is the second plan.
