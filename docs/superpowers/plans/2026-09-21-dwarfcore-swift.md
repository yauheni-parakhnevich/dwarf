# DwarfCore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `DwarfCore`, the Swift package holding every decision the gnome makes — motion detection, tracking, aiming, the firing rules and the BLE wire format — with no iOS frameworks, so all of it runs and is tested on a Mac in seconds.

**Architecture:** Pure value types and small classes with injected time. Nothing here imports UIKit, AVFoundation, CoreML or CoreBluetooth; the iOS app (a later plan) feeds this package frames and detections and executes the decisions it returns. Time is always a parameter, never read from a clock, so every rule is testable with a fake clock. The wire format is checked against the same `protocol/fixtures/*.json` the ESP32 firmware tests against, so the two sides cannot drift apart.

**Tech Stack:** Swift 6.4 toolchain, SwiftPM, XCTest, Foundation's JSON coders. No third-party dependencies.

**Specs:** `docs/superpowers/specs/2026-09-18-dwarf-cat-deterrent-design.md` §5 and §7, and `docs/superpowers/specs/2026-09-21-mechanical-design.md` §2 for why aiming is calibrated rather than modelled.

---

## Context the implementer needs

**What this thing does.** A phone inside a garden gnome watches the yard, finds cats, and tells an ESP32 where to point a nozzle and when to open a valve for a ~300 ms burst of water. This package is the deciding half. It never touches hardware.

**Why time is a parameter.** Every rule that matters — the 10 s gap between shots, the 3 s heartbeat, the 1 s window for judging whether a cat is standing still — is a timing rule. Passing `now` in means a test can advance time 5 seconds instantly and deterministically. A module that calls `Date()` internally is untestable and will be rejected in review.

**Two clocks, deliberately.** `uptime` is monotonic seconds since launch, used for every cooldown and interval; it never jumps. `now` is a wall-clock `Date`, used only to decide whether the current time of day falls inside the active window. Mixing them up is the obvious bug here: a user changing timezone must not reset a shot cooldown.

**Coordinates are normalised.** Every point and rectangle in this package is in 0...1 of frame width and height, origin top-left. Pixel sizes live in the iOS layer. This keeps the logic independent of whether a frame is 1080p or 4K, and means calibration survives a resolution change.

**The firmware already exists** and its behaviour is fixed. Read `firmware/lib/dwarf/protocol.cpp` before Task 8; it rejects any message with a missing field, a non-finite number, or an `ms` that is not an integer. `{"ms":300}` is accepted and `{"ms":300.0}` is rejected.

---

## File structure

| File | Responsibility |
|---|---|
| `ios/DwarfCore/Package.swift` | Package manifest: one library target, one test target |
| `Sources/DwarfCore/Geometry.swift` | `Point`, `Rect`, `Polygon` in normalised coordinates |
| `Sources/DwarfCore/GrayFrame.swift` | A downscaled grayscale frame and its mean luma |
| `Sources/DwarfCore/MotionDetector.swift` | Running-average background, thresholding, blobs |
| `Sources/DwarfCore/Scheduler.swift` | Which crops and sweep tiles the detector looks at this cycle |
| `Sources/DwarfCore/Tracking.swift` | `Detection`, `Track`, `Tracker`: association, confirmation, stillness |
| `Sources/DwarfCore/Masks.swift` | Ignore zones and the no-fire zone |
| `Sources/DwarfCore/Calibration.swift` | Calibration points, height offsets, JSON persistence |
| `Sources/DwarfCore/QuadraticFit.swift` | Least-squares surface fit and the linear solver behind it |
| `Sources/DwarfCore/Aimer.swift` | Image point → pan/tilt/range, body vs head, flagging |
| `Sources/DwarfCore/FirePolicy.swift` | Every welfare and safety rule; returns a decision |
| `Sources/DwarfCore/Protocol/Command.swift` | Phone → ESP32 messages |
| `Sources/DwarfCore/Protocol/Incoming.swift` | ESP32 → phone status and acks |
| `Sources/DwarfCore/Cycle.swift` | Wires the modules together for one camera frame |
| `Tests/DwarfCoreTests/*.swift` | One test file per source file, plus `FixtureTests.swift` |

**Dependency direction:** `Cycle` → {`MotionDetector`, `Scheduler`, `Tracker`, `Aimer`, `FirePolicy`, `Protocol`} → {`Calibration`, `Masks`, `QuadraticFit`, `GrayFrame`} → `Geometry`. Nothing points back up.

---

### Task 0: Package scaffold and geometry

**Files:**
- Create: `ios/DwarfCore/Package.swift`
- Create: `ios/DwarfCore/Sources/DwarfCore/Geometry.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/GeometryTests.swift`

- [ ] **Step 1: Create the package manifest**

Create `ios/DwarfCore/Package.swift`:

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DwarfCore",
    platforms: [.macOS(.v13), .iOS(.v15)],
    products: [
        .library(name: "DwarfCore", targets: ["DwarfCore"])
    ],
    targets: [
        .target(name: "DwarfCore"),
        .testTarget(name: "DwarfCoreTests", dependencies: ["DwarfCore"])
    ]
)
```

iOS 15 is the deployment target because the phone is an iPhone 6s, which cannot go higher. macOS 13 is only so the tests run locally.

- [ ] **Step 2: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/GeometryTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class GeometryTests: XCTestCase {
    func testRectDerivedPoints() {
        let r = Rect(x: 0.2, y: 0.4, width: 0.4, height: 0.2)
        XCTAssertEqual(r.center.x, 0.4, accuracy: 1e-9)
        XCTAssertEqual(r.center.y, 0.5, accuracy: 1e-9)
        XCTAssertEqual(r.bottomCenter.y, 0.6, accuracy: 1e-9)
        XCTAssertEqual(r.topCenter.y, 0.4, accuracy: 1e-9)
        XCTAssertEqual(r.bottomCenter.x, 0.4, accuracy: 1e-9)
    }

    func testPointDistance() {
        XCTAssertEqual(Point(x: 0, y: 0).distance(to: Point(x: 0.3, y: 0.4)), 0.5, accuracy: 1e-9)
    }

    func testPolygonContainment() {
        let square = Polygon(points: [
            Point(x: 0.2, y: 0.2), Point(x: 0.8, y: 0.2),
            Point(x: 0.8, y: 0.8), Point(x: 0.2, y: 0.8)
        ])
        XCTAssertTrue(square.contains(Point(x: 0.5, y: 0.5)))
        XCTAssertFalse(square.contains(Point(x: 0.1, y: 0.5)))
        XCTAssertFalse(square.contains(Point(x: 0.5, y: 0.9)))
    }

    func testConcavePolygonContainment() {
        // An L shape: the notch must not count as inside.
        let l = Polygon(points: [
            Point(x: 0.1, y: 0.1), Point(x: 0.5, y: 0.1), Point(x: 0.5, y: 0.5),
            Point(x: 0.9, y: 0.5), Point(x: 0.9, y: 0.9), Point(x: 0.1, y: 0.9)
        ])
        XCTAssertTrue(l.contains(Point(x: 0.2, y: 0.2)))
        XCTAssertTrue(l.contains(Point(x: 0.7, y: 0.7)))
        XCTAssertFalse(l.contains(Point(x: 0.7, y: 0.2)))
    }

    func testEmptyPolygonContainsNothing() {
        XCTAssertFalse(Polygon(points: []).contains(Point(x: 0.5, y: 0.5)))
    }
}
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test`
Expected: compilation failure, `cannot find 'Rect' in scope`.

- [ ] **Step 4: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Geometry.swift`:

```swift
import Foundation

/// A point in normalised frame coordinates: 0...1 across the frame, origin top-left.
/// Normalised rather than pixels so the logic — and any saved calibration — survives a
/// change of capture resolution.
public struct Point: Equatable, Codable, Sendable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }

    public func distance(to other: Point) -> Double {
        let dx = x - other.x
        let dy = y - other.y
        return (dx * dx + dy * dy).squareRoot()
    }
}

/// A rectangle in normalised frame coordinates.
public struct Rect: Equatable, Codable, Sendable {
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double

    public init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    public var center: Point { Point(x: x + width / 2, y: y + height / 2) }

    /// Where the subject meets the ground. This is the aiming key: the ground plane is
    /// fixed, so one ground point maps to exactly one pan/tilt pair.
    public var bottomCenter: Point { Point(x: x + width / 2, y: y + height) }

    /// Roughly where a cat's head is, used for aim beyond 4 m.
    public var topCenter: Point { Point(x: x + width / 2, y: y) }
}

/// A closed polygon in normalised coordinates, used for mask zones.
public struct Polygon: Equatable, Codable, Sendable {
    public var points: [Point]

    public init(points: [Point]) {
        self.points = points
    }

    /// Ray casting, which handles concave shapes correctly — a yard mask is rarely convex.
    public func contains(_ p: Point) -> Bool {
        guard points.count >= 3 else { return false }
        var inside = false
        var j = points.count - 1
        for i in points.indices {
            let a = points[i]
            let b = points[j]
            if (a.y > p.y) != (b.y > p.y) {
                let t = (p.y - a.y) / (b.y - a.y)
                if p.x < a.x + t * (b.x - a.x) { inside.toggle() }
            }
            j = i
        }
        return inside
    }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test`
Expected: `Executed 5 tests, with 0 failures`.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add DwarfCore package with normalised geometry"
```

---

### Task 1: Grayscale frame

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/GrayFrame.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/GrayFrameTests.swift`

The iOS layer downscales each camera frame to roughly 480×270 grayscale and hands it over as
plain bytes. This type is that hand-off, plus the mean luma the darkness check needs.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/GrayFrameTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class GrayFrameTests: XCTestCase {
    func testPixelAccess() {
        let frame = GrayFrame(width: 3, height: 2, pixels: [0, 1, 2, 3, 4, 5])
        XCTAssertEqual(frame.luma(x: 0, y: 0), 0)
        XCTAssertEqual(frame.luma(x: 2, y: 0), 2)
        XCTAssertEqual(frame.luma(x: 0, y: 1), 3)
        XCTAssertEqual(frame.luma(x: 2, y: 1), 5)
    }

    func testMeanLuma() {
        XCTAssertEqual(GrayFrame(width: 2, height: 2, pixels: [0, 100, 100, 200]).meanLuma,
                       100, accuracy: 1e-9)
    }

    func testMeanLumaOfEmptyFrameIsZero() {
        XCTAssertEqual(GrayFrame(width: 0, height: 0, pixels: []).meanLuma, 0, accuracy: 1e-9)
    }

    func testMismatchedPixelCountIsRejected() {
        XCTAssertNil(GrayFrame(validating: 2, height: 2, pixels: [1, 2, 3]))
        XCTAssertNotNil(GrayFrame(validating: 2, height: 2, pixels: [1, 2, 3, 4]))
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter GrayFrameTests`
Expected: `cannot find 'GrayFrame' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/GrayFrame.swift`:

```swift
import Foundation

/// One downscaled grayscale frame, row-major, 8 bits per pixel.
///
/// The iOS layer produces these at roughly 480×270 — small enough that background
/// subtraction over every pixel costs nothing, large enough that a cat at 6 m is still
/// several pixels across.
public struct GrayFrame: Equatable, Sendable {
    public let width: Int
    public let height: Int
    public let pixels: [UInt8]

    /// Trusting initialiser for callers that already know the buffer is the right size.
    public init(width: Int, height: Int, pixels: [UInt8]) {
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    /// Checking initialiser for anything crossing a boundary, such as a camera callback.
    public init?(validating width: Int, height: Int, pixels: [UInt8]) {
        guard width >= 0, height >= 0, pixels.count == width * height else { return nil }
        self.init(width: width, height: height, pixels: pixels)
    }

    public func luma(x: Int, y: Int) -> UInt8 {
        pixels[y * width + x]
    }

    /// Average brightness, used to pause detection once the yard goes dark.
    public var meanLuma: Double {
        guard !pixels.isEmpty else { return 0 }
        var total = 0
        for p in pixels { total += Int(p) }
        return Double(total) / Double(pixels.count)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter GrayFrameTests`
Expected: `Executed 4 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add grayscale frame type"
```

**Post-review addendum (applied in commit `9251a0f`):** two guards added after review.

1. **`luma(x:y:)` gained a `precondition` on both coordinates.** A negative `x` with a
   positive `y` can compute a flat index that lands *inside* the buffer, silently returning
   a pixel from the wrong row — corrupting a frame diff rather than crashing. `precondition`
   rather than `assert`, so it holds in release too; it is not on the hot path, because the
   motion detector iterates `pixels.indices` directly rather than calling the accessor. The
   doc comment says so, to stop a later reader "optimising" the check away.
2. **The trusting initialiser gained a debug-only `assert`** on `pixels.count == width *
   height`. A mismatched buffer otherwise produces a plausible-looking `meanLuma` over the
   wrong denominator with no signal at all. It stays `assert` rather than `precondition`
   because skipping that check is the whole reason this initialiser exists.

The trap itself cannot be tested in-process, so the added tests pin the boundary that must
*not* trap: every valid coordinate of a small frame, corners included. The suite is 11 tests
after this task.

---

### Task 2: Motion detector

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/MotionDetector.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/MotionDetectorTests.swift`

Motion detection is not the detector — it decides *where the expensive YOLO model looks*.
A false positive costs one wasted inference; a missed blob costs nothing, because the sweep
tiles in Task 3 cover the frame anyway. So this is tuned to be cheap and forgiving.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/MotionDetectorTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class MotionDetectorTests: XCTestCase {
    /// A frame of uniform grey with a brighter filled square at the given top-left.
    private func frame(width: Int = 40, height: Int = 30,
                       squareX: Int? = nil, squareY: Int = 0, squareSize: Int = 6) -> GrayFrame {
        var pixels = [UInt8](repeating: 100, count: width * height)
        if let sx = squareX {
            for y in squareY..<(squareY + squareSize) {
                for x in sx..<(sx + squareSize) {
                    pixels[y * width + x] = 200
                }
            }
        }
        return GrayFrame(width: width, height: height, pixels: pixels)
    }

    func testFirstFrameProducesNoBlobs() {
        let detector = MotionDetector()
        XCTAssertTrue(detector.process(frame()).isEmpty)
    }

    func testStaticSceneProducesNoBlobs() {
        let detector = MotionDetector()
        _ = detector.process(frame())
        XCTAssertTrue(detector.process(frame()).isEmpty)
        XCTAssertTrue(detector.process(frame()).isEmpty)
    }

    func testMovingSquareIsFound() {
        var config = MotionConfig()
        config.minBlobArea = 4
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        let blobs = detector.process(frame(squareX: 10, squareY: 8))
        XCTAssertEqual(blobs.count, 1)

        let box = blobs[0].boundingBox
        // The square spans x 10..<16 of 40 and y 8..<14 of 30, plus one pixel of dilation.
        XCTAssertEqual(box.x, 9.0 / 40.0, accuracy: 0.03)
        XCTAssertEqual(box.y, 7.0 / 30.0, accuracy: 0.03)
        XCTAssertGreaterThan(box.width, 0.1)
        XCTAssertGreaterThan(box.height, 0.15)
    }

    func testTwoSeparateSquaresBecomeTwoBlobs() {
        var config = MotionConfig()
        config.minBlobArea = 4
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        var pixels = [UInt8](repeating: 100, count: 40 * 30)
        for y in 4..<10 { for x in 4..<10 { pixels[y * 40 + x] = 200 } }
        for y in 18..<24 { for x in 28..<34 { pixels[y * 40 + x] = 200 } }
        let blobs = detector.process(GrayFrame(width: 40, height: 30, pixels: pixels))

        XCTAssertEqual(blobs.count, 2)
    }

    func testBlobsSmallerThanTheMinimumAreDropped() {
        var config = MotionConfig()
        config.minBlobArea = 200
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())
        XCTAssertTrue(detector.process(frame(squareX: 10, squareY: 8)).isEmpty)
    }

    func testBackgroundAbsorbsAStoppedObject() {
        var config = MotionConfig()
        config.minBlobArea = 4
        config.backgroundAlpha = 0.5   // absorb fast, so the test stays short
        let detector = MotionDetector(config: config)
        _ = detector.process(frame())

        let moved = frame(squareX: 10, squareY: 8)
        XCTAssertEqual(detector.process(moved).count, 1)
        for _ in 0..<12 { _ = detector.process(moved) }

        // This is exactly why the sweep tiles in the Scheduler exist: a cat that sits
        // still disappears from motion detection within seconds.
        XCTAssertTrue(detector.process(moved).isEmpty)
    }

    func testResetForgetsTheBackground() {
        let detector = MotionDetector()
        _ = detector.process(frame())
        detector.reset()
        XCTAssertTrue(detector.process(frame(squareX: 10, squareY: 8)).isEmpty,
                      "after reset the next frame is the new background, so nothing moves")
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter MotionDetectorTests`
Expected: `cannot find 'MotionDetector' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/MotionDetector.swift`:

```swift
import Foundation

public struct MotionConfig: Equatable, Sendable {
    /// How fast the background forgets. Higher absorbs a stopped object sooner.
    public var backgroundAlpha: Double = 0.05
    /// Absolute luma difference that counts as movement.
    public var threshold: Double = 25
    /// Blobs smaller than this many pixels are noise: leaves, rain, sensor grain.
    public var minBlobArea: Int = 20
    /// Grows each blob by this many pixels, closing the gaps inside one moving subject.
    public var dilationRadius: Int = 1

    public init() {}
}

public struct Blob: Equatable, Sendable {
    public let boundingBox: Rect
    public let area: Int

    public init(boundingBox: Rect, area: Int) {
        self.boundingBox = boundingBox
        self.area = area
    }
}

/// Finds moving regions by comparing each frame against a running average of the ones
/// before it.
///
/// Deliberately generous: its output only decides where the detector looks, and a missed
/// blob is covered by the Scheduler's sweep tiles.
public final class MotionDetector {
    public var config: MotionConfig
    private var background: [Double]?
    private var backgroundSize: (width: Int, height: Int)?

    public init(config: MotionConfig = MotionConfig()) {
        self.config = config
    }

    /// Forget the learned background. The next frame becomes the new one.
    public func reset() {
        background = nil
        backgroundSize = nil
    }

    public func process(_ frame: GrayFrame) -> [Blob] {
        guard frame.width > 0, frame.height > 0 else { return [] }

        // First frame, or the resolution changed: adopt it as the background and report
        // nothing. Reporting movement here would make every start-up a false alarm.
        guard var bg = background,
              let size = backgroundSize,
              size.width == frame.width, size.height == frame.height else {
            background = frame.pixels.map(Double.init)
            backgroundSize = (frame.width, frame.height)
            return []
        }

        var moving = [Bool](repeating: false, count: frame.pixels.count)
        for i in frame.pixels.indices {
            let value = Double(frame.pixels[i])
            moving[i] = abs(value - bg[i]) >= config.threshold
            bg[i] += config.backgroundAlpha * (value - bg[i])
        }
        background = bg

        let dilated = dilate(moving, width: frame.width, height: frame.height,
                             radius: config.dilationRadius)
        return components(dilated, width: frame.width, height: frame.height)
            .filter { $0.area >= config.minBlobArea }
    }

    private func dilate(_ mask: [Bool], width: Int, height: Int, radius: Int) -> [Bool] {
        guard radius > 0 else { return mask }
        var out = [Bool](repeating: false, count: mask.count)
        for y in 0..<height {
            for x in 0..<width where mask[y * width + x] {
                let yLow = max(0, y - radius), yHigh = min(height - 1, y + radius)
                let xLow = max(0, x - radius), xHigh = min(width - 1, x + radius)
                for yy in yLow...yHigh {
                    for xx in xLow...xHigh {
                        out[yy * width + xx] = true
                    }
                }
            }
        }
        return out
    }

    /// Four-connected labelling with an explicit stack: recursion would blow up on a blob
    /// covering a large part of the frame.
    private func components(_ mask: [Bool], width: Int, height: Int) -> [Blob] {
        var visited = [Bool](repeating: false, count: mask.count)
        var blobs: [Blob] = []
        var stack: [Int] = []

        for start in mask.indices where mask[start] && !visited[start] {
            visited[start] = true
            stack.removeAll(keepingCapacity: true)
            stack.append(start)

            var minX = width, maxX = -1, minY = height, maxY = -1, area = 0

            while let index = stack.popLast() {
                let x = index % width
                let y = index / width
                area += 1
                minX = min(minX, x); maxX = max(maxX, x)
                minY = min(minY, y); maxY = max(maxY, y)

                if x > 0 { push(index - 1, &stack, &visited, mask) }
                if x < width - 1 { push(index + 1, &stack, &visited, mask) }
                if y > 0 { push(index - width, &stack, &visited, mask) }
                if y < height - 1 { push(index + width, &stack, &visited, mask) }
            }

            blobs.append(Blob(
                boundingBox: Rect(
                    x: Double(minX) / Double(width),
                    y: Double(minY) / Double(height),
                    width: Double(maxX - minX + 1) / Double(width),
                    height: Double(maxY - minY + 1) / Double(height)
                ),
                area: area
            ))
        }
        return blobs
    }

    private func push(_ index: Int, _ stack: inout [Int], _ visited: inout [Bool], _ mask: [Bool]) {
        guard mask[index], !visited[index] else { return }
        visited[index] = true
        stack.append(index)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter MotionDetectorTests`
Expected: `Executed 7 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add motion detector with background subtraction"
```

---

### Task 3: Detector scheduler

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Scheduler.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/SchedulerTests.swift`

The A9 chip cannot run YOLO over a whole frame every cycle. This decides what it looks at:
crops around whatever moved, plus one tile of a rolling sweep. The sweep is what finds a cat
that has sat down and been absorbed into the background — which is exactly the cat we most
want to discourage.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/SchedulerTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class SchedulerTests: XCTestCase {
    private func blob(x: Double, y: Double) -> Blob {
        Blob(boundingBox: Rect(x: x, y: y, width: 0.05, height: 0.08), area: 50)
    }

    func testWithoutMotionItStillSweeps() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [])
        XCTAssertEqual(requests.count, 1)
        XCTAssertEqual(requests[0].kind, .sweep)
    }

    func testSweepTilesCycleAndCoverTheFrame() {
        let scheduler = Scheduler()   // default 2 columns x 1 row
        let first = scheduler.next(blobs: [])[0].rect
        let second = scheduler.next(blobs: [])[0].rect
        let third = scheduler.next(blobs: [])[0].rect

        XCTAssertNotEqual(first, second, "consecutive cycles must sweep different tiles")
        XCTAssertEqual(first, third, "two tiles means the cycle repeats on the third call")
        XCTAssertLessThan(first.x, second.x)
        // Together the tiles span the frame.
        XCTAssertEqual(first.x, 0, accuracy: 1e-9)
        XCTAssertEqual(second.x + second.width, 1, accuracy: 1e-9)
    }

    func testSweepTilesOverlap() {
        let scheduler = Scheduler()
        let left = scheduler.next(blobs: [])[0].rect
        let right = scheduler.next(blobs: [])[0].rect
        XCTAssertGreaterThan(left.x + left.width, right.x,
                             "tiles must overlap so a cat on the seam is not missed")
    }

    func testMotionCropsAreCentredOnBlobs() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [blob(x: 0.4, y: 0.4)])
        let crops = requests.filter { $0.kind == .motion }

        XCTAssertEqual(crops.count, 1)
        let expectedCentre = Point(x: 0.425, y: 0.44)
        XCTAssertEqual(crops[0].rect.center.x, expectedCentre.x, accuracy: 1e-6)
        XCTAssertEqual(crops[0].rect.center.y, expectedCentre.y, accuracy: 1e-6)
    }

    func testCropsAreClampedInsideTheFrame() {
        let scheduler = Scheduler()
        let requests = scheduler.next(blobs: [blob(x: 0.97, y: 0.95)])
        let crop = requests.first { $0.kind == .motion }!.rect

        XCTAssertGreaterThanOrEqual(crop.x, 0)
        XCTAssertGreaterThanOrEqual(crop.y, 0)
        XCTAssertLessThanOrEqual(crop.x + crop.width, 1 + 1e-9)
        XCTAssertLessThanOrEqual(crop.y + crop.height, 1 + 1e-9)
    }

    func testMotionCropsAreCappedAndPreferLargerBlobs() {
        var config = SchedulerConfig()
        config.maxMotionCrops = 2
        let scheduler = Scheduler(config: config)

        let small = Blob(boundingBox: Rect(x: 0.1, y: 0.1, width: 0.02, height: 0.02), area: 25)
        let medium = Blob(boundingBox: Rect(x: 0.5, y: 0.5, width: 0.04, height: 0.04), area: 120)
        let large = Blob(boundingBox: Rect(x: 0.8, y: 0.2, width: 0.06, height: 0.06), area: 400)

        let crops = scheduler.next(blobs: [small, medium, large]).filter { $0.kind == .motion }
        XCTAssertEqual(crops.count, 2)
        // Largest first: the biggest moving thing is the most likely cat.
        XCTAssertEqual(crops[0].rect.center.x, large.boundingBox.center.x, accuracy: 0.05)
        XCTAssertEqual(crops[1].rect.center.x, medium.boundingBox.center.x, accuracy: 0.05)
    }

    func testABlobBiggerThanTheCropGrowsTheCrop() {
        let scheduler = Scheduler()
        let huge = Blob(boundingBox: Rect(x: 0.2, y: 0.2, width: 0.5, height: 0.5), area: 5000)
        let crop = scheduler.next(blobs: [huge]).first { $0.kind == .motion }!.rect

        XCTAssertGreaterThanOrEqual(crop.width, 0.5)
        XCTAssertGreaterThanOrEqual(crop.height, 0.5)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter SchedulerTests`
Expected: `cannot find 'Scheduler' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Scheduler.swift`:

```swift
import Foundation

public struct SchedulerConfig: Equatable, Sendable {
    /// Crop size in normalised units. The defaults are a 640x640 pixel crop taken from a
    /// 1920x1080 frame, which is why they differ: 640/1920 wide, 640/1080 tall.
    public var cropWidth: Double = 640.0 / 1920.0
    public var cropHeight: Double = 640.0 / 1080.0
    /// How many motion crops to spend per cycle, largest blob first.
    public var maxMotionCrops: Int = 2
    /// Sweep grid. 2x1 covers a 1080p frame in two tiles of 960x1080.
    public var sweepColumns: Int = 2
    public var sweepRows: Int = 1
    /// Fraction of a tile that overlaps its neighbour, so a cat on the seam is still whole
    /// in at least one tile.
    public var sweepOverlap: Double = 0.12

    public init() {}
}

public struct CropRequest: Equatable, Sendable {
    public enum Kind: Equatable, Sendable {
        /// Something moved here this cycle.
        case motion
        /// Part of the rolling full-frame sweep.
        case sweep
    }

    public let rect: Rect
    public let kind: Kind

    public init(rect: Rect, kind: Kind) {
        self.rect = rect
        self.kind = kind
    }
}

/// Chooses what the detector looks at this cycle.
///
/// Motion crops react fast to a walking cat. The sweep is slower but finds a cat that has
/// stopped: once it stops moving, the motion detector's background absorbs it within
/// seconds and it would otherwise become invisible.
public final class Scheduler {
    public var config: SchedulerConfig
    private var nextTile = 0

    public init(config: SchedulerConfig = SchedulerConfig()) {
        self.config = config
    }

    public func next(blobs: [Blob]) -> [CropRequest] {
        var requests = blobs
            .sorted { $0.area > $1.area }
            .prefix(max(0, config.maxMotionCrops))
            .map { CropRequest(rect: crop(around: $0.boundingBox), kind: .motion) }

        requests.append(CropRequest(rect: sweepTile(), kind: .sweep))
        return requests
    }

    /// A crop centred on the blob, at least as large as the configured crop, grown if the
    /// blob itself is bigger, and clamped to the frame.
    private func crop(around box: Rect) -> Rect {
        let width = min(1, max(config.cropWidth, box.width))
        let height = min(1, max(config.cropHeight, box.height))
        let centre = box.center
        let x = min(max(0, centre.x - width / 2), 1 - width)
        let y = min(max(0, centre.y - height / 2), 1 - height)
        return Rect(x: x, y: y, width: width, height: height)
    }

    private func sweepTile() -> Rect {
        let columns = max(1, config.sweepColumns)
        let rows = max(1, config.sweepRows)
        let count = columns * rows
        let index = nextTile % count
        nextTile = (nextTile + 1) % count

        let column = index % columns
        let row = index / columns

        let baseWidth = 1.0 / Double(columns)
        let baseHeight = 1.0 / Double(rows)
        let width = min(1, baseWidth * (1 + config.sweepOverlap))
        let height = min(1, baseHeight * (1 + config.sweepOverlap))

        // Spread the tiles so the first starts at 0 and the last ends at 1, with the
        // overlap absorbed in between.
        let xSpan = columns > 1 ? (1 - width) / Double(columns - 1) : 0
        let ySpan = rows > 1 ? (1 - height) / Double(rows - 1) : 0

        return Rect(x: Double(column) * xSpan, y: Double(row) * ySpan,
                    width: width, height: height)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter SchedulerTests`
Expected: `Executed 7 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add detector scheduler with motion crops and sweep tiles"
```

**Post-review addendum (applied in commit `e337743`):** analysis of the committed version
found two design gaps, both fixed before later tasks built on this output.

1. **Crop size hardcoded the capture resolution.** `cropWidth = 640/1920` and
   `cropHeight = 640/1080` encoded an assumption the type could not check, and it would fail
   silently the day capture resolution changed — the pixel crop would stop being square and
   something downstream would have to letterbox or stretch it. The config now stores
   `cropPixels`, `frameWidthPixels` and `frameHeightPixels`, and derives the normalised crop
   from them, guarding division by zero and clamping into 0...1. A square model input is a
   pixel-space property, so it is now expressed in pixels. The defaults are numerically
   identical, so no existing test changed.
2. **The smallest blob could be starved forever.** Selection re-sorted by area every cycle
   and took the top N, so with a stable size ordering the smallest blob was *never* given a
   fitted crop — only ever glanced at by a sweep tile at a fraction of the effective
   resolution. That is exactly the small, distant cat the system most wants to discourage.
   The largest blob is still served every cycle, and the remaining slots now rotate through
   the rest, so every blob is served within `rest.count` cycles. No blob identity tracking
   was needed: the rotation walks positions in each cycle's freshly sorted list.

The suite is 29 tests after this task.

---

### Task 4: Tracker

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Tracking.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/TrackingTests.swift`

The tracker turns per-frame detections into things with history. Two properties matter
downstream, and both are safety properties:

- **Confirmed** — seen as a cat in 2 of the last 3 looks. One frame's confidence is not
  enough to justify spraying water at something.
- **Still** — barely moving. The design only fires at a stationary cat, because a shot takes
  about a second to arrive and leading a moving target reliably is beyond this machine.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/TrackingTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class TrackingTests: XCTestCase {
    private func detection(x: Double, y: Double, confidence: Double = 0.9) -> Detection {
        Detection(box: Rect(x: x, y: y, width: 0.08, height: 0.06), confidence: confidence)
    }

    func testFirstDetectionCreatesAnUnconfirmedTrack() {
        let tracker = Tracker()
        let tracks = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertFalse(tracks[0].isConfirmed, "one look is never enough to fire")
    }

    func testTwoOfThreeLooksConfirms() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.505, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertTrue(tracks[0].isConfirmed)
    }

    func testLowConfidenceDetectionsDoNotConfirm() {
        var config = TrackerConfig()
        config.minConfidence = 0.5
        let tracker = Tracker(config: config)

        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5, confidence: 0.3)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.5, y: 0.5, confidence: 0.35)], at: 0.1)

        XCTAssertEqual(tracks.count, 1)
        XCTAssertFalse(tracks[0].isConfirmed)
    }

    func testAMissedLookCountsAgainstConfirmation() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        _ = tracker.update(detections: [], at: 0.1)
        let tracks = tracker.update(detections: [], at: 0.2)

        XCTAssertEqual(tracks.count, 1, "the track survives briefly so it can be re-acquired")
        XCTAssertFalse(tracks[0].isConfirmed, "one hit in the last three looks is not enough")
    }

    func testNearbyDetectionsAssociateToTheSameTrack() {
        let tracker = Tracker()
        let first = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        let second = tracker.update(detections: [detection(x: 0.51, y: 0.5)], at: 0.1)

        XCTAssertEqual(first[0].id, second[0].id)
    }

    func testADistantDetectionStartsANewTrack() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.2, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.8, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 2)
        XCTAssertNotEqual(tracks[0].id, tracks[1].id)
    }

    func testTwoCatsKeepSeparateIdentities() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.2, y: 0.5), detection(x: 0.8, y: 0.5)], at: 0)
        let tracks = tracker.update(detections: [detection(x: 0.21, y: 0.5), detection(x: 0.79, y: 0.5)], at: 0.1)

        XCTAssertEqual(tracks.count, 2)
        XCTAssertEqual(Set(tracks.map(\.id)).count, 2)
    }

    func testAStationaryTrackIsStill() {
        let tracker = Tracker()
        var time = 0.0
        for _ in 0..<12 {
            _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: time)
            time += 0.1
        }
        XCTAssertTrue(tracker.tracks[0].isStill)
    }

    func testAWalkingTrackIsNotStill() {
        let tracker = Tracker()
        var time = 0.0
        var x = 0.2
        for _ in 0..<12 {
            _ = tracker.update(detections: [detection(x: x, y: 0.5)], at: time)
            time += 0.1
            x += 0.02   // 0.2 frame widths per second, well above the threshold
        }
        XCTAssertFalse(tracker.tracks[0].isStill)
    }

    func testANewTrackIsNotYetStill() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        XCTAssertFalse(tracker.tracks[0].isStill,
                       "stillness needs a full window of history, not one sample")
    }

    func testTracksAreDroppedAfterGoingUnseen() {
        let tracker = Tracker()
        _ = tracker.update(detections: [detection(x: 0.5, y: 0.5)], at: 0)
        _ = tracker.update(detections: [], at: 1.0)
        XCTAssertEqual(tracker.tracks.count, 1)

        let tracks = tracker.update(detections: [], at: 3.5)
        XCTAssertTrue(tracks.isEmpty)
    }

    func testGroundPointIsTheBottomOfTheBox() {
        let tracker = Tracker()
        let tracks = tracker.update(detections: [detection(x: 0.4, y: 0.3)], at: 0)
        XCTAssertEqual(tracks[0].groundPoint.y, 0.36, accuracy: 1e-9)
        XCTAssertEqual(tracks[0].groundPoint.x, 0.44, accuracy: 1e-9)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter TrackingTests`
Expected: `cannot find 'Detection' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Tracking.swift`:

```swift
import Foundation

/// One box the detector returned for one crop. Only cats reach here: the iOS layer filters
/// the model's classes before calling in.
public struct Detection: Equatable, Sendable {
    public let box: Rect
    public let confidence: Double

    public init(box: Rect, confidence: Double) {
        self.box = box
        self.confidence = confidence
    }
}

public struct TrackerConfig: Equatable, Sendable {
    /// Maximum distance between a track's ground point and a detection's, in normalised
    /// units, for the two to be considered the same animal.
    public var gate: Double = 0.05
    /// A track is confirmed at `confirmHits` positive looks out of the last `confirmWindow`.
    public var confirmHits: Int = 2
    public var confirmWindow: Int = 3
    /// Detections below this confidence do not count as a positive look.
    public var minConfidence: Double = 0.5
    /// Speed below which a track counts as still, in frame widths per second.
    public var stillSpeed: Double = 0.02
    /// How far back stillness is measured.
    public var stillWindow: TimeInterval = 1.0
    /// A track unseen for this long is forgotten.
    public var dropAfter: TimeInterval = 3.0

    public init() {}
}

public struct Track: Equatable, Identifiable, Sendable {
    public let id: Int
    public var box: Rect
    public var confidence: Double
    public var lastSeen: TimeInterval
    public var isConfirmed: Bool
    public var isStill: Bool

    /// Where the animal meets the ground: the aiming key.
    public var groundPoint: Point { box.bottomCenter }
    /// Roughly the head, used for aim beyond 4 m.
    public var headPoint: Point { box.topCenter }
}

/// Turns per-frame detections into tracks with enough history to fire on.
public final class Tracker {
    public var config: TrackerConfig

    private struct State {
        var id: Int
        var box: Rect
        var confidence: Double
        var lastSeen: TimeInterval
        /// Recent looks, newest last: true when the detector saw a confident cat.
        var looks: [Bool] = []
        /// Recent ground positions for the stillness test, newest last.
        var samples: [(time: TimeInterval, point: Point)] = []
    }

    private var states: [State] = []
    private var nextID = 1

    public init(config: TrackerConfig = TrackerConfig()) {
        self.config = config
    }

    public var tracks: [Track] { states.map(track(from:)) }

    public func update(detections: [Detection], at time: TimeInterval) -> [Track] {
        var unmatched = Array(detections.indices)

        // Greedy nearest-neighbour association. With at most a handful of cats in a
        // garden, anything cleverer is unjustified complexity.
        for index in states.indices {
            let ground = states[index].box.bottomCenter
            var bestSlot: Int?
            var bestDistance = config.gate

            for (slot, detectionIndex) in unmatched.enumerated() {
                let distance = detections[detectionIndex].box.bottomCenter.distance(to: ground)
                if distance <= bestDistance {
                    bestDistance = distance
                    bestSlot = slot
                }
            }

            if let slot = bestSlot {
                let detection = detections[unmatched[slot]]
                unmatched.remove(at: slot)
                states[index].box = detection.box
                states[index].confidence = detection.confidence
                states[index].lastSeen = time
                record(look: detection.confidence >= config.minConfidence, in: &states[index])
                states[index].samples.append((time, detection.box.bottomCenter))
            } else {
                // Seen nothing where this track was: that counts against confirmation.
                record(look: false, in: &states[index])
            }

            trimSamples(&states[index], now: time)
        }

        for detectionIndex in unmatched {
            let detection = detections[detectionIndex]
            var state = State(id: nextID, box: detection.box,
                              confidence: detection.confidence, lastSeen: time)
            nextID += 1
            record(look: detection.confidence >= config.minConfidence, in: &state)
            state.samples.append((time, detection.box.bottomCenter))
            states.append(state)
        }

        states.removeAll { time - $0.lastSeen > config.dropAfter }
        return tracks
    }

    private func record(look: Bool, in state: inout State) {
        state.looks.append(look)
        if state.looks.count > config.confirmWindow {
            state.looks.removeFirst(state.looks.count - config.confirmWindow)
        }
    }

    private func trimSamples(_ state: inout State, now: TimeInterval) {
        state.samples.removeAll { now - $0.time > config.stillWindow }
    }

    private func track(from state: State) -> Track {
        Track(
            id: state.id,
            box: state.box,
            confidence: state.confidence,
            lastSeen: state.lastSeen,
            isConfirmed: state.looks.filter { $0 }.count >= config.confirmHits,
            isStill: isStill(state)
        )
    }

    /// Still means: a full window of history exists, and the animal covered almost no
    /// ground across it. Demanding the full window stops a brand-new track from being
    /// declared still simply because it has only one sample.
    private func isStill(_ state: State) -> Bool {
        guard let first = state.samples.first, let last = state.samples.last else { return false }
        let elapsed = last.time - first.time
        guard elapsed >= config.stillWindow * 0.8 else { return false }
        return last.point.distance(to: first.point) / elapsed <= config.stillSpeed
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter TrackingTests`
Expected: `Executed 12 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add tracker with confirmation and stillness"
```

---

### Task 5: Mask zones

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Masks.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/MaskTests.swift`

Two kinds of zone, drawn by the owner in the web UI. **Ignore zones** are places whose
movement is noise — a road, a swaying tree, a neighbour's window. **No-fire zones** are
places that must never be sprayed, above all the area within about 2 m of the gnome, where
the jet is still a hard stream.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/MaskTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class MaskTests: XCTestCase {
    private var masks: MaskSet {
        MaskSet(
            ignoreZones: [Polygon(points: [
                Point(x: 0, y: 0), Point(x: 0.3, y: 0), Point(x: 0.3, y: 0.3), Point(x: 0, y: 0.3)
            ])],
            noFireZones: [Polygon(points: [
                Point(x: 0, y: 0.85), Point(x: 1, y: 0.85), Point(x: 1, y: 1), Point(x: 0, y: 1)
            ])]
        )
    }

    func testIgnoreZone() {
        XCTAssertTrue(masks.isIgnored(Point(x: 0.1, y: 0.1)))
        XCTAssertFalse(masks.isIgnored(Point(x: 0.5, y: 0.5)))
    }

    func testNoFireZone() {
        XCTAssertTrue(masks.isNoFire(Point(x: 0.5, y: 0.95)))
        XCTAssertFalse(masks.isNoFire(Point(x: 0.5, y: 0.5)))
    }

    func testZonesAreIndependent() {
        XCTAssertFalse(masks.isIgnored(Point(x: 0.5, y: 0.95)))
        XCTAssertFalse(masks.isNoFire(Point(x: 0.1, y: 0.1)))
    }

    func testEmptyMaskSetAllowsEverything() {
        let empty = MaskSet.empty
        XCTAssertFalse(empty.isIgnored(Point(x: 0.5, y: 0.5)))
        XCTAssertFalse(empty.isNoFire(Point(x: 0.5, y: 0.5)))
    }

    func testRoundTripsThroughJSON() throws {
        let data = try JSONEncoder().encode(masks)
        let decoded = try JSONDecoder().decode(MaskSet.self, from: data)
        XCTAssertEqual(decoded, masks)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter MaskTests`
Expected: `cannot find 'MaskSet' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Masks.swift`:

```swift
import Foundation

/// Zones the owner draws over the camera view.
public struct MaskSet: Equatable, Codable, Sendable {
    /// Movement inside these is discarded before it reaches the detector: a road, a tree
    /// that sways, a neighbour's window.
    public var ignoreZones: [Polygon]
    /// Never fire at anything standing here. Chiefly the ground within about 2 m of the
    /// gnome, where the jet is still a hard stream rather than spread spray.
    public var noFireZones: [Polygon]

    public init(ignoreZones: [Polygon] = [], noFireZones: [Polygon] = []) {
        self.ignoreZones = ignoreZones
        self.noFireZones = noFireZones
    }

    public static let empty = MaskSet()

    public func isIgnored(_ point: Point) -> Bool {
        ignoreZones.contains { $0.contains(point) }
    }

    public func isNoFire(_ point: Point) -> Bool {
        noFireZones.contains { $0.contains(point) }
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter MaskTests`
Expected: `Executed 5 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add mask zones"
```

---

### Task 6: Calibration types and the quadratic fit

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Calibration.swift`
- Create: `ios/DwarfCore/Sources/DwarfCore/QuadraticFit.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/QuadraticFitTests.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/CalibrationTests.swift`

Aiming is not computed from a model of the machine. During calibration the owner fires test
shots, clicks where the water landed and types the distance, and those samples are fitted
with a smooth surface. Every fixed offset — nozzle ahead of the pan axis, camera in the
belly, head height — is absorbed by the fit. See the mechanical spec §2.

The surface is `v = a0 + a1x + a2y + a3x² + a4xy + a5y²` per axis, solved by least squares
through the normal equations and Gaussian elimination with partial pivoting. Six unknowns,
so at least six points, and the plan demands eight for margin.

- [ ] **Step 1: Write the failing test for the fit**

Create `ios/DwarfCore/Tests/DwarfCoreTests/QuadraticFitTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class QuadraticFitTests: XCTestCase {
    /// Samples a known surface on a grid, so the fit has something exact to recover.
    private func samples(_ f: (Double, Double) -> Double) -> [(Point, Double)] {
        var out: [(Point, Double)] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.1, through: 0.9, by: 0.2) {
                out.append((Point(x: x, y: y), f(x, y)))
            }
        }
        return out
    }

    func testRecoversAPlane() throws {
        let fit = try XCTUnwrap(QuadraticFit.fit(samples { x, y in 3 + 2 * x - 5 * y }))
        XCTAssertEqual(fit.value(at: Point(x: 0.5, y: 0.5)), 3 + 1 - 2.5, accuracy: 1e-6)
        XCTAssertEqual(fit.value(at: Point(x: 0.2, y: 0.7)), 3 + 0.4 - 3.5, accuracy: 1e-6)
    }

    func testRecoversACurvedSurface() throws {
        let f: (Double, Double) -> Double = { x, y in 1 + 2 * x - 3 * y + 4 * x * x + 5 * x * y - 6 * y * y }
        let fit = try XCTUnwrap(QuadraticFit.fit(samples(f)))
        XCTAssertEqual(fit.value(at: Point(x: 0.35, y: 0.65)), f(0.35, 0.65), accuracy: 1e-6)
    }

    func testToleratesNoisySamples() throws {
        var noisy = samples { x, y in 10 + 4 * x - 2 * y }
        noisy[3].1 += 0.05
        noisy[7].1 -= 0.04
        let fit = try XCTUnwrap(QuadraticFit.fit(noisy))
        XCTAssertEqual(fit.value(at: Point(x: 0.5, y: 0.5)), 11, accuracy: 0.1)
    }

    func testTooFewPointsReturnsNil() {
        let five = Array(samples { x, _ in x }.prefix(5))
        XCTAssertNil(QuadraticFit.fit(five))
    }

    func testDegenerateLayoutReturnsNil() {
        // Every sample on one line: the surface is not determined.
        let collinear = (0..<10).map { i -> (Point, Double) in
            let t = Double(i) / 10
            return (Point(x: t, y: t), t)
        }
        XCTAssertNil(QuadraticFit.fit(collinear))
    }

    func testResidualReportsFitError() throws {
        let fit = try XCTUnwrap(QuadraticFit.fit(samples { x, y in x + y }))
        XCTAssertEqual(fit.residual(at: Point(x: 0.4, y: 0.4), expected: 0.8), 0, accuracy: 1e-6)
        XCTAssertEqual(fit.residual(at: Point(x: 0.4, y: 0.4), expected: 1.0), 0.2, accuracy: 1e-6)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter QuadraticFitTests`
Expected: `cannot find 'QuadraticFit' in scope`.

- [ ] **Step 3: Write the fit**

Create `ios/DwarfCore/Sources/DwarfCore/QuadraticFit.swift`:

```swift
import Foundation

/// A least-squares quadratic surface over normalised image coordinates:
/// `v = a0 + a1·x + a2·y + a3·x² + a4·x·y + a5·y²`.
///
/// Smooth, cheap, and sane a little outside the sampled area — which matters, because the
/// owner will not calibrate every corner of the yard.
public struct QuadraticFit: Equatable, Codable, Sendable {
    public let coefficients: [Double]   // exactly six

    public init?(coefficients: [Double]) {
        guard coefficients.count == 6 else { return nil }
        self.coefficients = coefficients
    }

    public func value(at p: Point) -> Double {
        let basis = QuadraticFit.basis(p)
        var sum = 0.0
        for i in 0..<6 { sum += coefficients[i] * basis[i] }
        return sum
    }

    public func residual(at p: Point, expected: Double) -> Double {
        abs(value(at: p) - expected)
    }

    static func basis(_ p: Point) -> [Double] {
        [1, p.x, p.y, p.x * p.x, p.x * p.y, p.y * p.y]
    }

    /// Fits the surface. Returns nil when there are fewer than six samples, or when they
    /// are laid out so the surface is not determined — all on one line, for instance.
    public static func fit(_ samples: [(Point, Double)]) -> QuadraticFit? {
        guard samples.count >= 6 else { return nil }

        // Normal equations: (AᵀA) c = Aᵀb.
        var ata = [[Double]](repeating: [Double](repeating: 0, count: 6), count: 6)
        var atb = [Double](repeating: 0, count: 6)

        for (point, value) in samples {
            let basis = basis(point)
            for i in 0..<6 {
                atb[i] += basis[i] * value
                for j in 0..<6 {
                    ata[i][j] += basis[i] * basis[j]
                }
            }
        }

        guard let solution = solve(ata, atb) else { return nil }
        return QuadraticFit(coefficients: solution)
    }

    /// Gaussian elimination with partial pivoting. Returns nil if the matrix is singular
    /// to within a tolerance, which is how a degenerate sample layout is detected.
    static func solve(_ matrix: [[Double]], _ rhs: [Double]) -> [Double]? {
        let n = rhs.count
        var a = matrix
        var b = rhs

        for column in 0..<n {
            var pivotRow = column
            var pivotValue = abs(a[column][column])
            for row in (column + 1)..<n where abs(a[row][column]) > pivotValue {
                pivotValue = abs(a[row][column])
                pivotRow = row
            }
            guard pivotValue > 1e-12 else { return nil }

            if pivotRow != column {
                a.swapAt(pivotRow, column)
                b.swapAt(pivotRow, column)
            }

            let pivot = a[column][column]
            for row in (column + 1)..<n {
                let factor = a[row][column] / pivot
                guard factor != 0 else { continue }
                for k in column..<n {
                    a[row][k] -= factor * a[column][k]
                }
                b[row] -= factor * b[column]
            }
        }

        var solution = [Double](repeating: 0, count: n)
        for row in stride(from: n - 1, through: 0, by: -1) {
            var sum = b[row]
            for k in (row + 1)..<n {
                sum -= a[row][k] * solution[k]
            }
            solution[row] = sum / a[row][row]
        }
        return solution.allSatisfy { $0.isFinite } ? solution : nil
    }
}
```

- [ ] **Step 4: Run the fit tests**

Run: `cd ios/DwarfCore && swift test --filter QuadraticFitTests`
Expected: `Executed 6 tests, with 0 failures`.

- [ ] **Step 5: Write the failing test for the calibration store**

Create `ios/DwarfCore/Tests/DwarfCoreTests/CalibrationTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class CalibrationTests: XCTestCase {
    private var sample: Calibration {
        Calibration(
            points: [
                CalibrationPoint(image: Point(x: 0.3, y: 0.8), pan: -12, tilt: -5, rangeM: 2.5),
                CalibrationPoint(image: Point(x: 0.5, y: 0.7), pan: 0, tilt: 2, rangeM: 4.0)
            ],
            heightOffsets: [
                HeightOffsetSample(rangeM: 4.0, deltaTiltDeg: 3.2),
                HeightOffsetSample(rangeM: 6.0, deltaTiltDeg: 2.1)
            ]
        )
    }

    func testRoundTripsThroughJSON() throws {
        let data = try JSONEncoder().encode(sample)
        XCTAssertEqual(try JSONDecoder().decode(Calibration.self, from: data), sample)
    }

    func testEmptyCalibrationIsEmpty() {
        XCTAssertTrue(Calibration.empty.points.isEmpty)
        XCTAssertTrue(Calibration.empty.heightOffsets.isEmpty)
    }

    func testHeightOffsetInterpolatesBetweenSamples() {
        XCTAssertEqual(sample.heightOffset(atRange: 5.0), 2.65, accuracy: 1e-9)
        XCTAssertEqual(sample.heightOffset(atRange: 4.5), 2.925, accuracy: 1e-9)
    }

    func testHeightOffsetClampsOutsideTheCalibratedSpan() {
        XCTAssertEqual(sample.heightOffset(atRange: 2.0), 3.2, accuracy: 1e-9)
        XCTAssertEqual(sample.heightOffset(atRange: 9.0), 2.1, accuracy: 1e-9)
    }

    func testHeightOffsetIsNilWithoutSamples() {
        XCTAssertNil(Calibration.empty.heightOffset(atRange: 5))
    }

    func testASingleHeightSampleAppliesEverywhere() {
        let one = Calibration(points: [], heightOffsets: [HeightOffsetSample(rangeM: 5, deltaTiltDeg: 2.7)])
        XCTAssertEqual(one.heightOffset(atRange: 2), 2.7, accuracy: 1e-9)
        XCTAssertEqual(one.heightOffset(atRange: 8), 2.7, accuracy: 1e-9)
    }
}
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter CalibrationTests`
Expected: `cannot find 'Calibration' in scope`.

- [ ] **Step 7: Write the calibration store**

Create `ios/DwarfCore/Sources/DwarfCore/Calibration.swift`:

```swift
import Foundation

/// One calibration shot: the owner fired at a spot, clicked where the water landed, and
/// typed how far away it was.
public struct CalibrationPoint: Equatable, Codable, Sendable {
    public var image: Point
    public var pan: Double
    public var tilt: Double
    public var rangeM: Double

    public init(image: Point, pan: Double, tilt: Double, rangeM: Double) {
        self.image = image
        self.pan = pan
        self.tilt = tilt
        self.rangeM = rangeM
    }
}

/// How much extra tilt raises the impact point by 25 cm at a given range — the difference
/// between hitting the ground under a cat and hitting the cat.
public struct HeightOffsetSample: Equatable, Codable, Sendable {
    public var rangeM: Double
    public var deltaTiltDeg: Double

    public init(rangeM: Double, deltaTiltDeg: Double) {
        self.rangeM = rangeM
        self.deltaTiltDeg = deltaTiltDeg
    }
}

/// Everything learned on the lawn, persisted as JSON by the iOS layer.
public struct Calibration: Equatable, Codable, Sendable {
    public var points: [CalibrationPoint]
    public var heightOffsets: [HeightOffsetSample]

    public init(points: [CalibrationPoint] = [], heightOffsets: [HeightOffsetSample] = []) {
        self.points = points
        self.heightOffsets = heightOffsets
    }

    public static let empty = Calibration()

    /// Linear interpolation by range, clamped at both ends. Nil when nothing was measured,
    /// which makes head aim impossible and is treated as such by the Aimer.
    public func heightOffset(atRange range: Double) -> Double? {
        let sorted = heightOffsets.sorted { $0.rangeM < $1.rangeM }
        guard let first = sorted.first, let last = sorted.last else { return nil }
        if range <= first.rangeM { return first.deltaTiltDeg }
        if range >= last.rangeM { return last.deltaTiltDeg }

        for (low, high) in zip(sorted, sorted.dropFirst()) where range >= low.rangeM && range <= high.rangeM {
            let span = high.rangeM - low.rangeM
            guard span > 0 else { return low.deltaTiltDeg }
            let t = (range - low.rangeM) / span
            return low.deltaTiltDeg + t * (high.deltaTiltDeg - low.deltaTiltDeg)
        }
        return last.deltaTiltDeg
    }
}
```

- [ ] **Step 8: Run the calibration tests**

Run: `cd ios/DwarfCore && swift test --filter CalibrationTests`
Expected: `Executed 6 tests, with 0 failures`.

- [ ] **Step 9: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add calibration store and quadratic surface fit"
```

---

### Task 7: Aimer

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Aimer.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/AimerTests.swift`

Turns a track into servo angles. Three fits: pan, tilt and range, all over the same
calibration points. Then the range decides what we aim at — body between 2 and 4 m where
the jet is still a hard stream, head beyond 4 m where it arrives as spread spray — and the
head case adds the calibrated height offset to the tilt.

The Aimer never decides *whether* to fire. It reports a solution and whether that solution
is trustworthy; `FirePolicy` decides.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/AimerTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class AimerTests: XCTestCase {
    /// A synthetic but plausible yard: pan follows x, tilt and range follow y.
    private func calibration(withHeightOffsets: Bool = true) -> Calibration {
        var points: [CalibrationPoint] = []
        for x in stride(from: 0.1, through: 0.9, by: 0.2) {
            for y in stride(from: 0.55, through: 0.95, by: 0.1) {
                let range = 8.0 - 6.0 * y          // y 0.55 -> 4.7 m, y 0.95 -> 2.3 m
                points.append(CalibrationPoint(
                    image: Point(x: x, y: y),
                    pan: (x - 0.5) * 100,          // -40 .. +40 degrees
                    tilt: 30 - 34 * y,             // further away means higher tilt
                    rangeM: range
                ))
            }
        }
        return Calibration(
            points: points,
            heightOffsets: withHeightOffsets
                ? [HeightOffsetSample(rangeM: 3, deltaTiltDeg: 4.0),
                   HeightOffsetSample(rangeM: 6, deltaTiltDeg: 2.0)]
                : []
        )
    }

    private func track(ground: Point, headOffsetY: Double = 0.06) -> Track {
        Track(id: 1,
              box: Rect(x: ground.x - 0.04, y: ground.y - headOffsetY, width: 0.08, height: headOffsetY),
              confidence: 0.9, lastSeen: 0, isConfirmed: true, isStill: true)
    }

    func testRefusesToBuildWithoutEnoughPoints() {
        let thin = Calibration(points: Array(calibration().points.prefix(5)))
        XCTAssertNil(Aimer(calibration: thin))
    }

    func testRecoversPanAndRange() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let solution = aimer.solve(for: track(ground: Point(x: 0.7, y: 0.75)))

        XCTAssertEqual(solution.pan, 20, accuracy: 1.5)
        XCTAssertEqual(solution.rangeM, 3.5, accuracy: 0.2)
        XCTAssertFalse(solution.isFlagged)
    }

    func testCloseRangeAimsAtTheBody() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.92)))   // ~2.5 m

        XCTAssertEqual(solution.target, .body)
        // Body aim is the ground solution with no height offset added.
        XCTAssertEqual(solution.tilt, 30 - 34 * 0.92, accuracy: 1.0)
    }

    func testLongRangeAimsAtTheHeadAndAddsTheHeightOffset() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let ground = Point(x: 0.5, y: 0.6)                                        // ~4.4 m
        let solution = aimer.solve(for: track(ground: ground))

        XCTAssertEqual(solution.target, .head)
        let groundTilt = 30 - 34 * 0.6
        let expectedOffset = try XCTUnwrap(calibration().heightOffset(atRange: solution.rangeM))
        XCTAssertEqual(solution.tilt, groundTilt + expectedOffset, accuracy: 1.0)
        XCTAssertGreaterThan(solution.tilt, groundTilt, "head aim must sit above ground aim")
    }

    func testHeadAimIsFlaggedWithoutAHeightOffsetTable() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration(withHeightOffsets: false)))
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.6)))

        XCTAssertEqual(solution.target, .head)
        XCTAssertTrue(solution.isFlagged, "no height data means the head solution is a guess")
    }

    func testSolutionsOutsideTheServoLimitsAreFlaggedAndClamped() throws {
        var limits = AimLimits()
        limits.panMax = 10
        let aimer = try XCTUnwrap(Aimer(calibration: calibration(), limits: limits))
        let solution = aimer.solve(for: track(ground: Point(x: 0.9, y: 0.8)))

        XCTAssertTrue(solution.isFlagged)
        XCTAssertLessThanOrEqual(solution.pan, 10)
    }

    func testPointsFarOutsideTheCalibratedAreaAreFlagged() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        // Calibration covers y 0.55...0.95; the top of the frame is the sky.
        let solution = aimer.solve(for: track(ground: Point(x: 0.5, y: 0.15)))
        XCTAssertTrue(solution.isFlagged)
    }

    func testResidualsReportPerPointError() throws {
        let aimer = try XCTUnwrap(Aimer(calibration: calibration()))
        let residuals = aimer.residuals()

        XCTAssertEqual(residuals.count, calibration().points.count)
        // The synthetic yard is exactly quadratic, so the fit should be near-perfect.
        XCTAssertLessThan(residuals.map(\.panError).max() ?? 99, 0.5)
        XCTAssertLessThan(residuals.map(\.tiltError).max() ?? 99, 0.5)
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter AimerTests`
Expected: `cannot find 'Aimer' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Aimer.swift`:

```swift
import Foundation

/// Mechanical travel limits. These must stay inside the printed hard stops, never the
/// other way round.
public struct AimLimits: Equatable, Codable, Sendable {
    public var panMin: Double = -60
    public var panMax: Double = 60
    public var tiltMin: Double = -30
    public var tiltMax: Double = 40

    public init() {}

    public func clampPan(_ v: Double) -> Double { min(max(v, panMin), panMax) }
    public func clampTilt(_ v: Double) -> Double { min(max(v, tiltMin), tiltMax) }
    public func contains(pan: Double, tilt: Double) -> Bool {
        pan >= panMin && pan <= panMax && tilt >= tiltMin && tilt <= tiltMax
    }
}

public enum AimTarget: String, Equatable, Sendable {
    /// Between 2 and 4 m, where the jet is still a hard stream.
    case body
    /// Beyond 4 m, where it arrives as spread spray.
    case head
}

public struct AimSolution: Equatable, Sendable {
    public let pan: Double
    public let tilt: Double
    public let rangeM: Double
    public let target: AimTarget
    /// True when this solution should not be fired on: outside the servo limits, outside
    /// the calibrated area, or a head shot with no height data behind it.
    public let isFlagged: Bool
    public let flagReason: String?
}

public struct AimerResidual: Equatable, Sendable {
    public let point: CalibrationPoint
    public let panError: Double
    public let tiltError: Double
    public let rangeError: Double
}

/// Maps an image point to servo angles, using only what was measured on the lawn.
public struct Aimer {
    public let limits: AimLimits
    /// Range at which aim moves from the body to the head.
    public var bodyHeadSplitM: Double = 4.0
    /// How far outside the calibrated area a point may sit before its solution is flagged.
    public var extrapolationMargin: Double = 0.08

    private let calibration: Calibration
    private let panFit: QuadraticFit
    private let tiltFit: QuadraticFit
    private let rangeFit: QuadraticFit
    private let area: Rect

    /// Nil when the calibration cannot support a fit: fewer than six points, or a
    /// degenerate layout such as every point on one line.
    public init?(calibration: Calibration, limits: AimLimits = AimLimits()) {
        guard let pan = QuadraticFit.fit(calibration.points.map { ($0.image, $0.pan) }),
              let tilt = QuadraticFit.fit(calibration.points.map { ($0.image, $0.tilt) }),
              let range = QuadraticFit.fit(calibration.points.map { ($0.image, $0.rangeM) })
        else { return nil }

        let xs = calibration.points.map(\.image.x)
        let ys = calibration.points.map(\.image.y)
        guard let minX = xs.min(), let maxX = xs.max(),
              let minY = ys.min(), let maxY = ys.max() else { return nil }

        self.calibration = calibration
        self.limits = limits
        self.panFit = pan
        self.tiltFit = tilt
        self.rangeFit = range
        self.area = Rect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
    }

    public func solve(for track: Track) -> AimSolution {
        solve(groundPoint: track.groundPoint, headPoint: track.headPoint)
    }

    public func solve(groundPoint: Point, headPoint: Point) -> AimSolution {
        let range = rangeFit.value(at: groundPoint)
        let target: AimTarget = range >= bodyHeadSplitM ? .head : .body

        // Pan comes from the point being aimed at; tilt always starts from the ground
        // solution, because that is what the calibration measured.
        let rawPan = panFit.value(at: target == .head ? headPoint : groundPoint)
        let groundTilt = tiltFit.value(at: groundPoint)

        var reason: String?
        var rawTilt = groundTilt

        if target == .head {
            if let offset = calibration.heightOffset(atRange: range) {
                rawTilt = groundTilt + offset
            } else {
                reason = "no height offset calibrated"
            }
        }

        if !isInsideCalibratedArea(groundPoint) {
            reason = reason ?? "outside the calibrated area"
        }
        if !limits.contains(pan: rawPan, tilt: rawTilt) {
            reason = reason ?? "outside servo limits"
        }
        if !rawPan.isFinite || !rawTilt.isFinite || !range.isFinite {
            reason = "fit produced a non-finite value"
        }

        return AimSolution(
            pan: limits.clampPan(rawPan.isFinite ? rawPan : 0),
            tilt: limits.clampTilt(rawTilt.isFinite ? rawTilt : 0),
            rangeM: range.isFinite ? range : 0,
            target: target,
            isFlagged: reason != nil,
            flagReason: reason
        )
    }

    /// How well the fit reproduces each calibration point. The web UI shows this so the
    /// owner knows where to add samples.
    public func residuals() -> [AimerResidual] {
        calibration.points.map { point in
            AimerResidual(
                point: point,
                panError: panFit.residual(at: point.image, expected: point.pan),
                tiltError: tiltFit.residual(at: point.image, expected: point.tilt),
                rangeError: rangeFit.residual(at: point.image, expected: point.rangeM)
            )
        }
    }

    /// The calibrated area is approximated by the bounding box of the sampled points plus
    /// a margin. A convex hull would be tighter, but the box is easy to reason about and
    /// errs toward flagging, which is the safe direction.
    private func isInsideCalibratedArea(_ p: Point) -> Bool {
        p.x >= area.x - extrapolationMargin &&
        p.x <= area.x + area.width + extrapolationMargin &&
        p.y >= area.y - extrapolationMargin &&
        p.y <= area.y + area.height + extrapolationMargin
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter AimerTests`
Expected: `Executed 8 tests, with 0 failures`.

If a test fails by a small margin, do not widen its tolerance: check whether the fit is
actually recovering the synthetic surface, since that is what the test exists to prove.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add aimer with body and head targeting"
```

---

### Task 8: Outgoing commands

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Protocol/Command.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/CommandTests.swift`

The ESP32 is unforgiving by design, because it is the thing holding the valve shut. Before
writing this, read `firmware/lib/dwarf/protocol.cpp`. Three rules it enforces:

1. A missing or wrong-typed field means the whole command is rejected, not defaulted.
2. A non-finite number is rejected. Our encoder must never produce one.
3. `ms` must be a JSON **integer**. `300` is accepted, `300.0` is rejected — and Swift's
   `Double` encodes 300 as `300`, so the type used here matters.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/CommandTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class CommandTests: XCTestCase {
    private func json(_ command: Command) throws -> [String: Any] {
        let data = try command.encoded()
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testHeartbeat() throws {
        XCTAssertEqual(try json(.heartbeat)["c"] as? String, "hb")
        XCTAssertEqual(try json(.heartbeat).count, 1)
    }

    func testArm() throws {
        let object = try json(.arm(true))
        XCTAssertEqual(object["c"] as? String, "arm")
        XCTAssertEqual(object["v"] as? Bool, true)
    }

    func testAim() throws {
        let object = try json(.aim(pan: 12.5, tilt: -3))
        XCTAssertEqual(object["c"] as? String, "aim")
        XCTAssertEqual(object["pan"] as? Double, 12.5)
        XCTAssertEqual(object["tilt"] as? Double, -3)
    }

    func testShootEncodesMsAsAnInteger() throws {
        let data = try Command.shoot(pan: 14, tilt: -2.5, ms: 300).encoded()
        let text = try XCTUnwrap(String(data: data, encoding: .utf8))

        // The firmware rejects "ms":300.0 outright, so this is not cosmetic.
        XCTAssertTrue(text.contains("\"ms\":300"), text)
        XCTAssertFalse(text.contains("300.0"), text)
    }

    func testPark() throws {
        XCTAssertEqual(try json(.park)["c"] as? String, "park")
    }

    func testChargeAndFan() throws {
        XCTAssertEqual(try json(.charge(false))["v"] as? Bool, false)
        XCTAssertEqual(try json(.fan(true))["c"] as? String, "fan")
    }

    func testConfig() throws {
        let object = try json(.config(panMin: -60, panMax: 60, tiltMin: -30, tiltMax: 40))
        XCTAssertEqual(object["c"] as? String, "cfg")
        XCTAssertEqual(object["panMin"] as? Double, -60)
        XCTAssertEqual(object["tiltMax"] as? Double, 40)
    }

    func testNonFiniteAnglesAreRefused() {
        XCTAssertThrowsError(try Command.aim(pan: .nan, tilt: 0).encoded())
        XCTAssertThrowsError(try Command.aim(pan: .infinity, tilt: 0).encoded())
        XCTAssertThrowsError(try Command.shoot(pan: 0, tilt: -.infinity, ms: 300).encoded())
        XCTAssertThrowsError(try Command.config(panMin: -60, panMax: .nan, tiltMin: -30, tiltMax: 40).encoded())
    }

    func testZeroLengthBurstIsRefused() {
        // The firmware rejects it too, but there is no reason to spend a BLE round trip
        // discovering that.
        XCTAssertThrowsError(try Command.shoot(pan: 0, tilt: 0, ms: 0).encoded())
    }

    func testEveryMessageFitsOneBLEWrite() throws {
        let commands: [Command] = [
            .heartbeat, .arm(true), .aim(pan: -59.9, tilt: -29.9), .park,
            .shoot(pan: -59.9, tilt: 39.9, ms: 500), .charge(false), .fan(true),
            .config(panMin: -60, panMax: 60, tiltMin: -30, tiltMax: 40)
        ]
        for command in commands {
            XCTAssertLessThanOrEqual(try command.encoded().count, 180, "\(command)")
        }
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter CommandTests`
Expected: `cannot find 'Command' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Protocol/Command.swift`:

```swift
import Foundation

/// A message from the phone to the ESP32. See spec §7.
public enum Command: Equatable, Sendable {
    case heartbeat
    case arm(Bool)
    case aim(pan: Double, tilt: Double)
    case park
    case shoot(pan: Double, tilt: Double, ms: UInt16)
    case charge(Bool)
    case fan(Bool)
    case config(panMin: Double, panMax: Double, tiltMin: Double, tiltMax: Double)

    public enum EncodingError: Error, Equatable {
        /// An angle was NaN or infinite. The firmware rejects these, and sending one
        /// would mean a silently dropped command.
        case nonFiniteValue(field: String)
        /// A zero-length burst. The firmware rejects it as "bad".
        case zeroBurst
    }

    public func encoded() throws -> Data {
        var object: [String: Any]

        switch self {
        case .heartbeat:
            object = ["c": "hb"]
        case .arm(let on):
            object = ["c": "arm", "v": on]
        case .aim(let pan, let tilt):
            try check(pan, "pan")
            try check(tilt, "tilt")
            object = ["c": "aim", "pan": pan, "tilt": tilt]
        case .park:
            object = ["c": "park"]
        case .shoot(let pan, let tilt, let ms):
            try check(pan, "pan")
            try check(tilt, "tilt")
            guard ms > 0 else { throw EncodingError.zeroBurst }
            // Int, not Double: the firmware requires a JSON integer here.
            object = ["c": "shoot", "pan": pan, "tilt": tilt, "ms": Int(ms)]
        case .charge(let on):
            object = ["c": "charge", "v": on]
        case .fan(let on):
            object = ["c": "fan", "v": on]
        case .config(let panMin, let panMax, let tiltMin, let tiltMax):
            try check(panMin, "panMin")
            try check(panMax, "panMax")
            try check(tiltMin, "tiltMin")
            try check(tiltMax, "tiltMax")
            object = ["c": "cfg", "panMin": panMin, "panMax": panMax,
                      "tiltMin": tiltMin, "tiltMax": tiltMax]
        }

        return try JSONSerialization.data(withJSONObject: object, options: [])
    }

    private func check(_ value: Double, _ field: String) throws {
        guard value.isFinite else { throw EncodingError.nonFiniteValue(field: field) }
    }
}
```

`JSONSerialization` is used rather than `JSONEncoder` because it lets a single message mix a
`Double` for the angles with an `Int` for `ms`, which is precisely the distinction the
firmware cares about.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter CommandTests`
Expected: `Executed 10 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): encode outgoing BLE commands"
```

---

### Task 9: Incoming status and acks, checked against the firmware's fixtures

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Protocol/Incoming.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/IncomingTests.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/FixtureTests.swift`

This is the task that keeps the two halves of the project honest. `protocol/fixtures/` holds
the canonical messages; the firmware's native tests already check its formatter against them,
and now the Swift side checks its parser against the same file. Change one side and the other
side's tests fail, instead of the gnome failing in the yard.

- [ ] **Step 1: Write the failing test for decoding**

Create `ios/DwarfCore/Tests/DwarfCoreTests/IncomingTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class IncomingTests: XCTestCase {
    private func decode(_ text: String) throws -> IncomingMessage {
        try IncomingMessage.decode(Data(text.utf8))
    }

    func testDecodesStatus() throws {
        let message = try decode(#"{"armed":true,"pan":12.5,"tilt":-3,"tank":"ok","pump":true,"charge":false,"fan":false,"temp":31.3,"fault":null,"shots":12}"#)
        guard case .status(let status) = message else { return XCTFail("expected status") }

        XCTAssertTrue(status.armed)
        XCTAssertEqual(status.pan, 12.5, accuracy: 1e-9)
        XCTAssertEqual(status.tilt, -3, accuracy: 1e-9)
        XCTAssertTrue(status.tankOk)
        XCTAssertTrue(status.pump)
        XCTAssertFalse(status.charge)
        XCTAssertEqual(status.temp, 31.3, accuracy: 1e-9)
        XCTAssertNil(status.fault)
        XCTAssertEqual(status.shots, 12)
    }

    func testDecodesEveryFaultCode() throws {
        let codes: [(String, DeviceFault)] = [
            ("TANK_EMPTY", .tankEmpty), ("OVERTEMP", .overtemp),
            ("TEMP_SENSOR", .tempSensor), ("VALVE_TIMEOUT", .valveTimeout)
        ]
        for (text, expected) in codes {
            let message = try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"low","pump":false,"charge":true,"fan":false,"temp":24,"fault":"\#(text)","shots":3}"#)
            guard case .status(let status) = message else { return XCTFail("expected status") }
            XCTAssertEqual(status.fault, expected)
            XCTAssertFalse(status.tankOk)
        }
    }

    func testAnUnknownFaultCodeDecodesAsUnknownRatherThanFailing() throws {
        // A newer firmware must not make the app blind to the rest of the status.
        let message = try decode(#"{"armed":false,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":24,"fault":"FUTURE_FAULT","shots":0}"#)
        guard case .status(let status) = message else { return XCTFail("expected status") }
        XCTAssertEqual(status.fault, .unknown("FUTURE_FAULT"))
    }

    func testDecodesRejectAck() throws {
        let message = try decode(#"{"ack":"shoot","ok":false,"why":"cooldown"}"#)
        guard case .ack(let ack) = message else { return XCTFail("expected ack") }

        XCTAssertEqual(ack.command, "shoot")
        XCTAssertFalse(ack.ok)
        XCTAssertEqual(ack.why, "cooldown")
    }

    func testDecodesSuccessAckWithoutWhy() throws {
        let message = try decode(#"{"ack":"arm","ok":true}"#)
        guard case .ack(let ack) = message else { return XCTFail("expected ack") }
        XCTAssertTrue(ack.ok)
        XCTAssertNil(ack.why)
    }

    func testRejectsGarbage() {
        XCTAssertThrowsError(try decode("not json"))
        XCTAssertThrowsError(try decode("{}"))
        XCTAssertThrowsError(try decode(#"{"hello":"world"}"#))
    }

    func testRejectsAStatusMissingAField() {
        XCTAssertThrowsError(try decode(#"{"armed":true,"pan":0,"tilt":0,"tank":"ok","pump":false,"charge":true,"fan":false,"temp":20,"fault":null}"#),
                             "shots is missing")
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter IncomingTests`
Expected: `cannot find 'IncomingMessage' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Protocol/Incoming.swift`:

```swift
import Foundation

/// A latched fault reported by the ESP32.
public enum DeviceFault: Equatable, Sendable {
    case tankEmpty
    case overtemp
    case tempSensor
    case valveTimeout
    /// A code this build does not know. Kept rather than discarded so a firmware newer
    /// than the app still shows something useful instead of looking healthy.
    case unknown(String)

    public init(code: String) {
        switch code {
        case "TANK_EMPTY": self = .tankEmpty
        case "OVERTEMP": self = .overtemp
        case "TEMP_SENSOR": self = .tempSensor
        case "VALVE_TIMEOUT": self = .valveTimeout
        default: self = .unknown(code)
        }
    }
}

/// The device state the ESP32 notifies about once a second and on every change.
public struct DeviceStatus: Equatable, Sendable {
    public let armed: Bool
    public let pan: Double
    public let tilt: Double
    public let tankOk: Bool
    public let pump: Bool
    public let charge: Bool
    public let fan: Bool
    public let temp: Double
    public let fault: DeviceFault?
    public let shots: UInt32

    /// Whether the device is in a state where a shot could be accepted at all. The full
    /// decision lives in FirePolicy; this is just the device's half of it.
    public var canFire: Bool { armed && tankOk && fault == nil }
}

/// The reply to a command. `why` is present only when `ok` is false.
public struct DeviceAck: Equatable, Sendable {
    public let command: String
    public let ok: Bool
    public let why: String?
}

public enum IncomingMessage: Equatable, Sendable {
    case status(DeviceStatus)
    case ack(DeviceAck)

    public enum DecodingError: Error, Equatable {
        case notAnObject
        case unrecognised
        case missingField(String)
    }

    public static func decode(_ data: Data) throws -> IncomingMessage {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw DecodingError.notAnObject
        }

        if let command = object["ack"] as? String {
            guard let ok = object["ok"] as? Bool else { throw DecodingError.missingField("ok") }
            return .ack(DeviceAck(command: command, ok: ok, why: object["why"] as? String))
        }

        guard object["armed"] != nil else { throw DecodingError.unrecognised }

        func number(_ key: String) throws -> Double {
            guard let value = object[key] as? NSNumber else { throw DecodingError.missingField(key) }
            return value.doubleValue
        }
        func flag(_ key: String) throws -> Bool {
            guard let value = object[key] as? Bool else { throw DecodingError.missingField(key) }
            return value
        }

        guard let tank = object["tank"] as? String else { throw DecodingError.missingField("tank") }

        let faultCode = object["fault"] as? String   // JSON null decodes to NSNull, not String

        return .status(DeviceStatus(
            armed: try flag("armed"),
            pan: try number("pan"),
            tilt: try number("tilt"),
            tankOk: tank == "ok",
            pump: try flag("pump"),
            charge: try flag("charge"),
            fan: try flag("fan"),
            temp: try number("temp"),
            fault: faultCode.map(DeviceFault.init(code:)),
            shots: UInt32(try number("shots"))
        ))
    }
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter IncomingTests`
Expected: `Executed 7 tests, with 0 failures`.

- [ ] **Step 5: Write the fixture cross-check**

Create `ios/DwarfCore/Tests/DwarfCoreTests/FixtureTests.swift`:

```swift
import XCTest
@testable import DwarfCore

/// Cross-checks this package against the same fixture files the ESP32 firmware's tests use.
/// If these fail, the two halves of the project have drifted apart.
final class FixtureTests: XCTestCase {
    /// Walk up from this source file to the repository root. Using #filePath rather than
    /// bundled resources keeps one copy of the fixtures, shared with the firmware.
    private func fixture(_ name: String) throws -> [String: String] {
        let here = URL(fileURLWithPath: #filePath)
        let root = here
            .deletingLastPathComponent()   // DwarfCoreTests
            .deletingLastPathComponent()   // Tests
            .deletingLastPathComponent()   // DwarfCore
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
        let url = root.appendingPathComponent("protocol/fixtures/\(name).json")
        let data = try Data(contentsOf: url)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])
    }

    func testEveryStatusFixtureDecodes() throws {
        for (name, text) in try fixture("status") {
            let message = try IncomingMessage.decode(Data(text.utf8))
            switch (name, message) {
            case ("ack_reject", .ack(let ack)):
                XCTAssertFalse(ack.ok)
                XCTAssertEqual(ack.why, "cooldown")
            case ("ack_ok", .ack(let ack)):
                XCTAssertTrue(ack.ok)
                XCTAssertNil(ack.why)
            case ("idle", .status(let status)):
                XCTAssertFalse(status.armed)
                XCTAssertNil(status.fault)
            case ("tank_empty", .status(let status)):
                XCTAssertEqual(status.fault, .tankEmpty)
                XCTAssertFalse(status.tankOk)
            case ("overtemp", .status(let status)):
                XCTAssertEqual(status.fault, .overtemp)
            case ("armed_shooting", .status(let status)):
                XCTAssertTrue(status.armed)
                XCTAssertTrue(status.pump)
                XCTAssertEqual(status.shots, 12)
            default:
                XCTFail("unhandled fixture \(name): add a case so new fixtures cannot slip in unchecked")
            }
        }
    }

    func testOurCommandsMatchTheCommandFixtures() throws {
        let fixtures = try fixture("commands")

        func assertMatches(_ command: Command, _ name: String,
                           file: StaticString = #filePath, line: UInt = #line) throws {
            let expectedText = try XCTUnwrap(fixtures[name], "missing fixture \(name)", file: file, line: line)
            let expected = try XCTUnwrap(
                JSONSerialization.jsonObject(with: Data(expectedText.utf8)) as? [String: Any],
                file: file, line: line)
            let actual = try XCTUnwrap(
                JSONSerialization.jsonObject(with: command.encoded()) as? [String: Any],
                file: file, line: line)

            XCTAssertEqual(Set(expected.keys), Set(actual.keys), "keys differ for \(name)",
                           file: file, line: line)
            for key in expected.keys {
                let lhs = expected[key], rhs = actual[key]
                if let l = lhs as? String, let r = rhs as? String {
                    XCTAssertEqual(l, r, "\(name).\(key)", file: file, line: line)
                } else if let l = lhs as? Bool, let r = rhs as? Bool {
                    XCTAssertEqual(l, r, "\(name).\(key)", file: file, line: line)
                } else if let l = lhs as? NSNumber, let r = rhs as? NSNumber {
                    XCTAssertEqual(l.doubleValue, r.doubleValue, accuracy: 1e-9,
                                   "\(name).\(key)", file: file, line: line)
                } else {
                    XCTFail("type mismatch for \(name).\(key)", file: file, line: line)
                }
            }
        }

        try assertMatches(.heartbeat, "hb")
        try assertMatches(.arm(true), "arm_on")
        try assertMatches(.arm(false), "arm_off")
        try assertMatches(.aim(pan: 12.5, tilt: -3.0), "aim")
        try assertMatches(.park, "park")
        try assertMatches(.shoot(pan: 14.0, tilt: -2.5, ms: 300), "shoot")
        try assertMatches(.charge(false), "charge_off")
        try assertMatches(.fan(true), "fan_on")
        try assertMatches(.config(panMin: -60, panMax: 60, tiltMin: -30, tiltMax: 40), "cfg")
    }
}
```

Comparison is by parsed object, not by byte, because JSON key order is not meaningful on the
wire and neither side guarantees it. Types and values are compared exactly.

- [ ] **Step 6: Run the fixture tests**

Run: `cd ios/DwarfCore && swift test --filter FixtureTests`
Expected: `Executed 2 tests, with 0 failures`.

If the file cannot be found, print the URL being opened and check the number of
`deletingLastPathComponent()` calls against the real depth of the package. If a status
fixture fails to decode, do **not** loosen the decoder: the firmware's own tests assert that
same string, so a mismatch means a real disagreement worth understanding.

- [ ] **Step 7: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): decode device status and check both sides against the fixtures"
```

---

### Task 10: Fire policy

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/FirePolicy.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/FirePolicyTests.swift`

This is the file where the project's ethics live. Everything else finds cats; this decides
whether water actually leaves the nozzle. The ESP32 enforces its own hard limits underneath —
500 ms per burst, 5 s between shots — but those are a backstop, not the policy. Every rule
below must hold before a shot is requested:

| Rule | Why |
|---|---|
| Mode is `live` | Dry-run exists so a week of logs can be reviewed before any water flows |
| Track is confirmed | Two of three looks, not one hopeful frame |
| Track is still | A shot takes about a second to arrive; leading a walking cat is beyond this machine |
| Range at least 2 m | Closer than that the jet is a hard stream, not spread spray |
| Ground point outside every no-fire zone | The owner drew those for a reason |
| Aim solution not flagged | Outside the servo limits, outside the calibrated area, or a head shot with no height data |
| Inside the active window | Daytime only |
| Scene not dark | The camera cannot tell a cat from a shadow at dusk |
| ≥10 s since this track's last shot | A cat needs time to leave |
| ≤3 shots at this track | It is a deterrent, not a punishment |
| ≤20 shots this hour | A cap on the whole system, whatever the tracker thinks it sees |
| Device armed, tank ok, no fault | The ESP32's own view of itself |

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/FirePolicyTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class FirePolicyTests: XCTestCase {
    /// Midday, well inside the active window.
    private func noon() -> Date {
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15
        components.hour = 12; components.minute = 0
        return Calendar.current.date(from: components)!
    }

    private func night() -> Date {
        var components = DateComponents()
        components.year = 2026; components.month = 6; components.day = 15
        components.hour = 23; components.minute = 30
        return Calendar.current.date(from: components)!
    }

    private func track(id: Int = 1, x: Double = 0.5, y: Double = 0.7,
                       confirmed: Bool = true, still: Bool = true) -> Track {
        Track(id: id,
              box: Rect(x: x - 0.04, y: y - 0.06, width: 0.08, height: 0.06),
              confidence: 0.9, lastSeen: 0, isConfirmed: confirmed, isStill: still)
    }

    private func healthyStatus() -> DeviceStatus {
        DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: true, pump: true,
                     charge: false, fan: false, temp: 22, fault: nil, shots: 0)
    }

    private func solution(range: Double = 5, flagged: Bool = false) -> AimSolution {
        AimSolution(pan: 12, tilt: 4, rangeM: range,
                    target: range >= 4 ? .head : .body,
                    isFlagged: flagged, flagReason: flagged ? "test" : nil)
    }

    private func input(mode: Mode = .live, tracks: [Track]? = nil,
                       masks: MaskSet = .empty, status: DeviceStatus? = nil,
                       luma: Double = 120, now: Date? = nil, uptime: TimeInterval = 100,
                       range: Double = 5, flagged: Bool = false) -> PolicyInput {
        PolicyInput(
            mode: mode,
            tracks: tracks ?? [track()],
            solutions: [1: solution(range: range, flagged: flagged)],
            masks: masks,
            status: status ?? healthyStatus(),
            meanLuma: luma,
            now: now ?? noon(),
            uptime: uptime
        )
    }

    // MARK: firing

    func testFiresWhenEverythingIsSatisfied() {
        let policy = FirePolicy()
        guard case .shoot(let pan, let tilt, let ms) = policy.decide(input()) else {
            return XCTFail("expected a shot")
        }
        XCTAssertEqual(pan, 12, accuracy: 1e-9)
        XCTAssertEqual(tilt, 4, accuracy: 1e-9)
        XCTAssertEqual(ms, 300)
    }

    func testDryRunReportsWithoutFiring() {
        let policy = FirePolicy()
        guard case .wouldShoot = policy.decide(input(mode: .dryRun)) else {
            return XCTFail("expected a logged would-shoot")
        }
    }

    func testDisarmedModeDoesNothing() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(mode: .disarmed)), .none)
    }

    // MARK: the track itself

    func testAnUnconfirmedTrackIsOnlyTracked() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)])) else {
            return XCTFail("expected the head to follow but not fire")
        }
    }

    func testAMovingTrackIsFollowedNotFired() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(still: false)])) else {
            return XCTFail("expected aim only")
        }
    }

    func testAnIgnoredZoneTrackIsNotEvenFollowed() {
        let zone = MaskSet(ignoreZones: [Polygon(points: [
            Point(x: 0.4, y: 0.6), Point(x: 0.6, y: 0.6),
            Point(x: 0.6, y: 0.8), Point(x: 0.4, y: 0.8)
        ])])
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(masks: zone, uptime: 100)), .none)
    }

    // MARK: welfare limits

    func testTooCloseIsNeverFired() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(range: 1.5)) else {
            return XCTFail("inside 2 m the jet is a hard stream: follow, never fire")
        }
    }

    func testNoFireZoneBlocksTheShot() {
        let zone = MaskSet(noFireZones: [Polygon(points: [
            Point(x: 0.3, y: 0.6), Point(x: 0.7, y: 0.6),
            Point(x: 0.7, y: 0.9), Point(x: 0.3, y: 0.9)
        ])])
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(masks: zone)) else {
            return XCTFail("expected aim only")
        }
    }

    func testAFlaggedSolutionBlocksTheShot() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(flagged: true)) else {
            return XCTFail("expected aim only")
        }
    }

    func testOutsideTheActiveWindowNothingFires() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(now: night())), .none)
    }

    func testDarknessStopsEverything() {
        let policy = FirePolicy()
        XCTAssertEqual(policy.decide(input(luma: 12)), .none)
    }

    // MARK: cooldowns and caps

    func testTheSameTrackCannotBeShotTwiceInTenSeconds() {
        let policy = FirePolicy()
        guard case .shoot = policy.decide(input(uptime: 100)) else { return XCTFail("first shot") }

        guard case .aim = policy.decide(input(uptime: 105)) else {
            return XCTFail("5 s later must not fire again")
        }
        guard case .shoot = policy.decide(input(uptime: 111)) else {
            return XCTFail("11 s later is allowed")
        }
    }

    func testATrackIsOnlyShotThreeTimes() {
        let policy = FirePolicy()
        var time = 100.0
        for _ in 0..<3 {
            guard case .shoot = policy.decide(input(uptime: time)) else {
                return XCTFail("expected a shot at \(time)")
            }
            time += 11
        }
        guard case .aim = policy.decide(input(uptime: time)) else {
            return XCTFail("the fourth shot at one cat is harassment, not deterrence")
        }
    }

    func testTheHourlyCapAppliesAcrossTracks() {
        var limits = FireLimits()
        limits.maxShotsPerHour = 2
        let policy = FirePolicy(limits: limits)
        var time = 100.0

        for id in 1...2 {
            guard case .shoot = policy.decide(PolicyInput(
                mode: .live, tracks: [track(id: id)], solutions: [id: solution()],
                masks: .empty, status: healthyStatus(), meanLuma: 120,
                now: noon(), uptime: time)) else { return XCTFail("shot \(id)") }
            time += 11
        }

        guard case .aim = policy.decide(PolicyInput(
            mode: .live, tracks: [track(id: 3)], solutions: [3: solution()],
            masks: .empty, status: healthyStatus(), meanLuma: 120,
            now: noon(), uptime: time)) else { return XCTFail("cap should hold") }
    }

    func testTheHourlyCapExpires() {
        var limits = FireLimits()
        limits.maxShotsPerHour = 1
        let policy = FirePolicy(limits: limits)

        guard case .shoot = policy.decide(input(uptime: 100)) else { return XCTFail("first") }
        guard case .aim = policy.decide(input(tracks: [track(id: 2)],
                                              uptime: 200)) else { return XCTFail("still capped") }
        guard case .shoot = policy.decide(PolicyInput(
            mode: .live, tracks: [track(id: 2)], solutions: [2: solution()],
            masks: .empty, status: healthyStatus(), meanLuma: 120,
            now: noon(), uptime: 100 + 3601)) else { return XCTFail("an hour later is fine") }
    }

    // MARK: the device's own state

    func testADisarmedDeviceIsNotFiredAt() {
        let status = DeviceStatus(armed: false, pan: 0, tilt: 0, tankOk: true, pump: false,
                                  charge: true, fan: false, temp: 22, fault: nil, shots: 0)
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(status: status)) else { return XCTFail("expected aim") }
    }

    func testAnEmptyTankBlocksTheShot() {
        let status = DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: false, pump: false,
                                  charge: true, fan: false, temp: 22, fault: .tankEmpty, shots: 0)
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(status: status)) else { return XCTFail("expected aim") }
    }

    func testAMissingStatusBlocksTheShot() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(PolicyInput(
            mode: .live, tracks: [track()], solutions: [1: solution()], masks: .empty,
            status: nil, meanLuma: 120, now: noon(), uptime: 100)) else {
            return XCTFail("no status means no idea whether it is safe to fire")
        }
    }

    // MARK: following and parking

    func testAimIsThrottled() {
        let policy = FirePolicy()
        // An unconfirmed track is followed but never fired at, which isolates aiming.
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("first aim")
        }
        XCTAssertEqual(policy.decide(input(tracks: [track(confirmed: false)], uptime: 100.1)), .none,
                       "aim at 5 Hz, not at frame rate")
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100.3)) else {
            return XCTFail("after the throttle interval, aim again")
        }
    }

    func testTheHeadParksAfterTheCatLeaves() {
        let policy = FirePolicy()
        guard case .aim = policy.decide(input(tracks: [track(confirmed: false)], uptime: 100)) else {
            return XCTFail("aim")
        }
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 105)), .none)
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 111)), .park)
        XCTAssertEqual(policy.decide(input(tracks: [], uptime: 112)), .none,
                       "park once, not repeatedly")
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter FirePolicyTests`
Expected: `cannot find 'FirePolicy' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/FirePolicy.swift`:

```swift
import Foundation

public enum Mode: String, Equatable, Codable, Sendable {
    case disarmed
    case dryRun = "dry-run"
    case live
    case calibration
}

public struct FireLimits: Equatable, Sendable {
    /// Shortest gap between two shots at the same animal.
    public var minShotInterval: TimeInterval = 10
    /// A deterrent, not a punishment.
    public var maxShotsPerTrack: Int = 3
    /// A ceiling on the whole system, whatever the tracker believes it is seeing.
    public var maxShotsPerHour: Int = 20
    public var burstMs: UInt16 = 300
    /// Active window in local time, as hours.
    public var activeStartHour: Int = 7
    public var activeEndHour: Int = 20
    /// Mean luma below which the scene is too dark to judge.
    public var darkLuma: Double = 40
    /// Closer than this the jet is a hard stream; never fire.
    public var minRangeM: Double = 2
    /// Aim updates per second while following a cat.
    public var aimInterval: TimeInterval = 0.2
    /// Idle time before the head returns to centre.
    public var parkAfter: TimeInterval = 10

    public init() {}
}

/// Everything the policy needs for one decision. Passed in rather than read, so the rules
/// are testable with a fake clock.
public struct PolicyInput: Sendable {
    public var mode: Mode
    public var tracks: [Track]
    /// Aim solutions by track id. A track without one cannot be fired at.
    public var solutions: [Int: AimSolution]
    public var masks: MaskSet
    /// The last status from the ESP32, or nil if none has arrived.
    public var status: DeviceStatus?
    public var meanLuma: Double
    /// Wall clock, used only for the active window.
    public var now: Date
    /// Monotonic seconds, used for every interval and cooldown.
    public var uptime: TimeInterval

    public init(mode: Mode, tracks: [Track], solutions: [Int: AimSolution], masks: MaskSet,
                status: DeviceStatus?, meanLuma: Double, now: Date, uptime: TimeInterval) {
        self.mode = mode
        self.tracks = tracks
        self.solutions = solutions
        self.masks = masks
        self.status = status
        self.meanLuma = meanLuma
        self.now = now
        self.uptime = uptime
    }
}

public enum FireDecision: Equatable, Sendable {
    case none
    case aim(pan: Double, tilt: Double)
    case shoot(pan: Double, tilt: Double, ms: UInt16)
    /// Dry-run: everything passed, but no water. Logged for review.
    case wouldShoot(pan: Double, tilt: Double, ms: UInt16)
    case park
}

/// Decides what the gnome does this cycle. The only place in the project allowed to ask for
/// water.
public final class FirePolicy {
    public var limits: FireLimits

    private var shotsByTrack: [Int: Int] = [:]
    private var lastShotByTrack: [Int: TimeInterval] = [:]
    private var recentShots: [TimeInterval] = []
    private var lastAim: TimeInterval?
    private var lastActivity: TimeInterval?
    private var parked = true

    public init(limits: FireLimits = FireLimits()) {
        self.limits = limits
    }

    public func decide(_ input: PolicyInput) -> FireDecision {
        guard input.mode != .disarmed, input.mode != .calibration else { return .none }
        guard isDaylight(input) else { return .none }

        let candidates = input.tracks
            .filter { !input.masks.isIgnored($0.groundPoint) }
            .sorted { $0.confidence > $1.confidence }

        guard let best = candidates.first else {
            return parkIfIdle(input.uptime)
        }

        lastActivity = input.uptime
        parked = false

        guard let solution = input.solutions[best.id] else {
            return aimIfDue(pan: nil, tilt: nil, at: input.uptime)
        }

        if canFire(best, solution, input) {
            record(shot: best.id, at: input.uptime)
            lastAim = input.uptime
            return input.mode == .live
                ? .shoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
                : .wouldShoot(pan: solution.pan, tilt: solution.tilt, ms: limits.burstMs)
        }

        return aimIfDue(pan: solution.pan, tilt: solution.tilt, at: input.uptime)
    }

    /// Every condition, in one place. Each line is a rule from the spec.
    private func canFire(_ track: Track, _ solution: AimSolution, _ input: PolicyInput) -> Bool {
        guard input.mode == .live || input.mode == .dryRun else { return false }
        guard track.isConfirmed, track.isStill else { return false }
        guard !solution.isFlagged else { return false }
        guard solution.rangeM >= limits.minRangeM else { return false }
        guard !input.masks.isNoFire(track.groundPoint) else { return false }
        guard let status = input.status, status.canFire else { return false }
        guard shotsByTrack[track.id, default: 0] < limits.maxShotsPerTrack else { return false }
        guard shotsInLastHour(endingAt: input.uptime) < limits.maxShotsPerHour else { return false }
        if let last = lastShotByTrack[track.id],
           input.uptime - last < limits.minShotInterval { return false }
        return true
    }

    private func isDaylight(_ input: PolicyInput) -> Bool {
        guard input.meanLuma >= limits.darkLuma else { return false }
        let hour = Calendar.current.component(.hour, from: input.now)
        return hour >= limits.activeStartHour && hour < limits.activeEndHour
    }

    private func aimIfDue(pan: Double?, tilt: Double?, at uptime: TimeInterval) -> FireDecision {
        guard let pan, let tilt else { return .none }
        if let last = lastAim, uptime - last < limits.aimInterval { return .none }
        lastAim = uptime
        return .aim(pan: pan, tilt: tilt)
    }

    private func parkIfIdle(_ uptime: TimeInterval) -> FireDecision {
        guard !parked else { return .none }
        guard let last = lastActivity, uptime - last >= limits.parkAfter else { return .none }
        parked = true
        lastAim = nil
        return .park
    }

    private func record(shot id: Int, at uptime: TimeInterval) {
        shotsByTrack[id, default: 0] += 1
        lastShotByTrack[id] = uptime
        recentShots.append(uptime)
    }

    private func shotsInLastHour(endingAt uptime: TimeInterval) -> Int {
        recentShots.removeAll { uptime - $0 > 3600 }
        return recentShots.count
    }
}
```

Note that a dry-run shot consumes the same budget a live one would. The point of dry-run is
to produce a week of logs that predict what live operation will do, and a run that ignored
its own cooldowns would predict nothing.

- [ ] **Step 4: Run it to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter FirePolicyTests`
Expected: `Executed 20 tests, with 0 failures`.

- [ ] **Step 5: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): add fire policy with welfare limits"
```

---

### Task 11: Cycle

**Files:**
- Create: `ios/DwarfCore/Sources/DwarfCore/Cycle.swift`
- Test: `ios/DwarfCore/Tests/DwarfCoreTests/CycleTests.swift`

One object that runs a frame through the whole pipeline, so the iOS layer has a single call
to make and one place to look when behaviour surprises it. It owns the stateful pieces —
motion detector, scheduler, tracker, policy — and takes the frame, the detections the model
produced for the crops it asked for last time, and the latest device status.

Detection is asynchronous in the real app: the crops requested this cycle come back a cycle
or two later. `Cycle` does not try to hide that. It returns the crops it wants next, and
accepts whatever detections have arrived.

- [ ] **Step 1: Write the failing test**

Create `ios/DwarfCore/Tests/DwarfCoreTests/CycleTests.swift`:

```swift
import XCTest
@testable import DwarfCore

final class CycleTests: XCTestCase {
    private func noon() -> Date {
        var c = DateComponents()
        c.year = 2026; c.month = 6; c.day = 15; c.hour = 12
        return Calendar.current.date(from: c)!
    }

    private func brightFrame(width: Int = 40, height: Int = 30) -> GrayFrame {
        GrayFrame(width: width, height: height, pixels: [UInt8](repeating: 120, count: width * height))
    }

    private func darkFrame(width: Int = 40, height: Int = 30) -> GrayFrame {
        GrayFrame(width: width, height: height, pixels: [UInt8](repeating: 5, count: width * height))
    }

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

    private func healthyStatus() -> DeviceStatus {
        DeviceStatus(armed: true, pan: 0, tilt: 0, tankOk: true, pump: true,
                     charge: false, fan: false, temp: 22, fault: nil, shots: 0)
    }

    private func cat(x: Double = 0.5, y: Double = 0.72) -> Detection {
        Detection(box: Rect(x: x - 0.04, y: y - 0.06, width: 0.08, height: 0.06), confidence: 0.9)
    }

    func testAlwaysAsksForSomethingToLookAt() {
        let cycle = Cycle(calibration: calibration())
        let output = cycle.process(frame: brightFrame(), detections: [], status: healthyStatus(),
                                   now: noon(), uptime: 0)
        XCTAssertFalse(output.cropRequests.isEmpty, "the sweep runs even with nothing moving")
    }

    func testAStillConfirmedCatEventuallyGetsShot() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .live   // Cycle defaults to dry-run, deliberately
        var uptime = 0.0
        var decisions: [FireDecision] = []

        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            decisions.append(output.decision)
            uptime += 0.1
        }

        XCTAssertTrue(decisions.contains { if case .shoot = $0 { return true } else { return false } },
                      "a confirmed, still cat in range should be fired at: \(decisions)")
    }

    func testDarknessSuppressesEverything() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .live
        var uptime = 0.0
        for _ in 0..<15 {
            let output = cycle.process(frame: darkFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            XCTAssertEqual(output.decision, .none)
            uptime += 0.1
        }
    }

    func testTracksAreExposedForTheUI() {
        let cycle = Cycle(calibration: calibration())
        let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                   status: healthyStatus(), now: noon(), uptime: 0)
        XCTAssertEqual(output.tracks.count, 1)
        XCTAssertEqual(output.solutions.count, 1)
    }

    func testWithoutCalibrationItStillTracksButNeverFires() {
        // An uncalibrated gnome must still run, otherwise it could never be calibrated.
        let cycle = Cycle(calibration: .empty)
        cycle.mode = .live

        var uptime = 0.0
        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            XCTAssertFalse(output.tracks.isEmpty, "tracking works without calibration")
            XCTAssertTrue(output.solutions.isEmpty, "but there are no aim solutions")
            if case .shoot = output.decision { XCTFail("fired without calibration") }
            uptime += 0.1
        }
    }

    func testModeIsRespected() {
        let cycle = Cycle(calibration: calibration())
        cycle.mode = .dryRun
        var uptime = 0.0
        var sawWouldShoot = false

        for _ in 0..<15 {
            let output = cycle.process(frame: brightFrame(), detections: [cat()],
                                       status: healthyStatus(), now: noon(), uptime: uptime)
            if case .wouldShoot = output.decision { sawWouldShoot = true }
            if case .shoot = output.decision { XCTFail("dry-run must not fire") }
            uptime += 0.1
        }
        XCTAssertTrue(sawWouldShoot)
    }
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ios/DwarfCore && swift test --filter CycleTests`
Expected: `cannot find 'Cycle' in scope`.

- [ ] **Step 3: Write the implementation**

Create `ios/DwarfCore/Sources/DwarfCore/Cycle.swift`:

```swift
import Foundation

/// What one cycle produced: what to do now, what the detector should look at next, and
/// enough state for the web UI to draw.
public struct CycleOutput: Sendable {
    public let decision: FireDecision
    public let cropRequests: [CropRequest]
    public let tracks: [Track]
    public let solutions: [Int: AimSolution]
    public let blobs: [Blob]
    public let meanLuma: Double
}

/// Runs a frame through the whole pipeline.
///
/// Owns the stateful parts. Detection happens outside and arrives late — the crops asked for
/// this cycle come back a cycle or two later — and this class does not pretend otherwise.
public final class Cycle {
    public var mode: Mode = .dryRun
    public var masks: MaskSet = .empty

    private let motion: MotionDetector
    private let scheduler: Scheduler
    private let tracker: Tracker
    private let policy: FirePolicy
    private var aimer: Aimer?

    /// Never fails. The *aimer* is what may be absent: an uncalibrated gnome must still
    /// boot, track and show a live view, otherwise it could never be calibrated in the
    /// first place. Without an aimer nothing can be fired, because FirePolicy requires a
    /// solution for the track it is considering.
    public init(calibration: Calibration,
                 limits: AimLimits = AimLimits(),
                 fireLimits: FireLimits = FireLimits(),
                 motionConfig: MotionConfig = MotionConfig(),
                 schedulerConfig: SchedulerConfig = SchedulerConfig(),
                 trackerConfig: TrackerConfig = TrackerConfig()) {
        self.motion = MotionDetector(config: motionConfig)
        self.scheduler = Scheduler(config: schedulerConfig)
        self.tracker = Tracker(config: trackerConfig)
        self.policy = FirePolicy(limits: fireLimits)
        self.aimer = Aimer(calibration: calibration, limits: limits)
    }

    /// Replaces the calibration, for instance right after the owner adds a point in the
    /// web UI.
    public func update(calibration: Calibration, limits: AimLimits = AimLimits()) {
        aimer = Aimer(calibration: calibration, limits: limits)
    }

    public func process(frame: GrayFrame,
                        detections: [Detection],
                        status: DeviceStatus?,
                        now: Date,
                        uptime: TimeInterval) -> CycleOutput {
        let blobs = motion.process(frame)
        let requests = scheduler.next(blobs: blobs)
        let tracks = tracker.update(detections: detections, at: uptime)

        var solutions: [Int: AimSolution] = [:]
        if let aimer {
            for track in tracks {
                solutions[track.id] = aimer.solve(for: track)
            }
        }

        let decision = policy.decide(PolicyInput(
            mode: mode,
            tracks: tracks,
            solutions: solutions,
            masks: masks,
            status: status,
            meanLuma: frame.meanLuma,
            now: now,
            uptime: uptime
        ))

        return CycleOutput(decision: decision, cropRequests: requests, tracks: tracks,
                           solutions: solutions, blobs: blobs, meanLuma: frame.meanLuma)
    }
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd ios/DwarfCore && swift test --filter CycleTests`
Expected: `Executed 6 tests, with 0 failures`.

- [ ] **Step 5: Run the whole suite**

Run: `cd ios/DwarfCore && swift test`
Expected: every test passes, roughly 85 of them, in a couple of seconds.

- [ ] **Step 6: Commit**

```bash
git add ios/DwarfCore
git commit -m "feat(core): wire the pipeline together in Cycle"
```

---

## Definition of done

- `swift test` passes in `ios/DwarfCore`, with no warnings.
- Nothing in `Sources/` imports UIKit, AVFoundation, CoreML or CoreBluetooth. Check with
  `grep -rE "import (UIKit|AVFoundation|CoreML|CoreBluetooth)" Sources/` — it must print
  nothing.
- No source file calls `Date()` or `CACurrentMediaTime()`. Time arrives as a parameter.
  Check with `grep -rn "Date()" Sources/`.
- `FixtureTests` passes against `protocol/fixtures/`, the same files the firmware tests use.
- Every welfare rule in the table at the head of Task 10 has a test that fails when the rule
  is removed.

## What this plan deliberately leaves out

- **CoreML and the camera.** They belong to the DwarfApp plan, along with the web UI, the
  event store and the BLE transport.
- **The replay harness.** It needs the real model to be interesting, so it belongs with the
  app.
- **Leading a moving target.** v1 fires only at a still cat; see the parent spec.
- **Owner-cat recognition.** Out of scope for v1.
- **Persistence.** `Calibration` and `MaskSet` are `Codable`; deciding where the JSON lives
  is the app's business.
