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
    .venv-model/bin/pip install -r tools/requirements-model.txt
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
.venv-model/bin/pip install -r tools/requirements-model.txt
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

The expected shape, which Task 5's code assumes: one image input at `imgsz × imgsz`, and two outputs — `confidence` of shape `(N, 80)` and `coordinates` of shape `(N, 4)`, the coordinates being `[x_center, y_center, width, height]` normalised to the input square. **If the real spec differs, stop and report it** rather than adapting Task 5 quietly.

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
