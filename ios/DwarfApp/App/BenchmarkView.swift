import SwiftUI
import CoreVideo
import DwarfAdapters

/// Runs the model over a synthetic input as fast as it can, and reports what the phone
/// actually sustains. Synthetic on purpose: this measures the model and the thermals, not
/// the camera, and a fixed input makes two runs comparable.
///
/// Deliberately a plain class dispatching to a global queue rather than anything built on
/// `Task`. `SwiftUI.View` is `@MainActor`-isolated, so an `async` method declared on a view
/// inherits that isolation and `Task.detached` hops straight back to the main actor to call
/// it — which is how the first version of this screen ran ten minutes of CoreML inference on
/// the main thread and got the app killed by the watchdog. Nothing in the type system warns
/// about it; the crash report's heaviest stack showed CoreFoundation's run loop calling into
/// Espresso.
final class BenchmarkRunner {
    private let queue = DispatchQueue(label: "garden.dwarf.benchmark", qos: .userInitiated)

    func start(report: @escaping (String, Bool) -> Void) {
        queue.async {
            guard let detector = try? CoreMLDetector(),
                  let input = FakeDetector.blankInput(side: 640) else {
                DispatchQueue.main.async { report("could not load the model", true) }
                return
            }

            let started = ProcessInfo.processInfo.systemUptime
            var count = 0
            var worstThermal = ProcessInfo.processInfo.thermalState
            var lastReport = started

            while ProcessInfo.processInfo.systemUptime - started < 600 {
                // CoreML autoreleases a good deal per call: the feature provider, both
                // output arrays and their storage. This loop never returns to a run loop,
                // so without an explicit pool nothing drains and the footprint climbs until
                // iOS kills the app.
                autoreleasepool {
                    _ = try? detector.detect(input: input)
                }
                count += 1

                let state = ProcessInfo.processInfo.thermalState
                if state.rawValue > worstThermal.rawValue { worstThermal = state }

                let now = ProcessInfo.processInfo.systemUptime
                if now - lastReport >= 5 {
                    lastReport = now
                    let line = String(format: "%.0f s · %d inferences · %.2f /s · thermal %d · %d MB",
                                      now - started, count, Double(count) / (now - started),
                                      worstThermal.rawValue, Self.residentMegabytes())
                    DispatchQueue.main.async { report(line, false) }
                }
            }

            let elapsed = ProcessInfo.processInfo.systemUptime - started
            let line = String(format: "DONE %.0f s · %d inferences · %.2f /s · worst thermal %d · %d MB",
                              elapsed, count, Double(count) / elapsed,
                              worstThermal.rawValue, Self.residentMegabytes())
            DispatchQueue.main.async { report(line, true) }
        }
    }

    /// Resident footprint, reported alongside the rate. A number that climbs steadily rather
    /// than settling means the pool problem above has come back.
    private static func residentMegabytes() -> Int {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? Int(info.resident_size / 1_048_576) : -1
    }
}

struct BenchmarkView: View {
    @State private var line = "idle"
    @State private var running = false
    private let runner = BenchmarkRunner()

    var body: some View {
        VStack(spacing: 16) {
            Text("M0 — inference benchmark").font(.headline)
            Text(line).font(.system(.body, design: .monospaced)).multilineTextAlignment(.center)
            Button(running ? "running…" : "run for 10 minutes") {
                running = true
                runner.start { text, finished in
                    line = text
                    if finished { running = false }
                }
            }
            .disabled(running)
            .padding(.top, 8)
        }
        .padding()
    }
}
