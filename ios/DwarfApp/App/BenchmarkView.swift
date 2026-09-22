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
                .padding(.top, 8)
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
            // Each inference autoreleases a good deal: CoreML's feature providers, the two
            // output MLMultiArrays and their backing storage. A tight loop inside a
            // detached task never returns to a run loop, so without an explicit pool
            // nothing ever drains and the footprint climbs until iOS kills the app. On a
            // 2 GB phone that takes a couple of minutes, which reads as "it ran for a
            // while and then crashed".
            autoreleasepool {
                _ = try? detector.detect(input: input)
            }
            count += 1

            let state = ProcessInfo.processInfo.thermalState
            if state.rawValue > worstThermal.rawValue { worstThermal = state }

            let now = ProcessInfo.processInfo.systemUptime
            if now - lastReport >= 5 {
                lastReport = now
                let rate = Double(count) / (now - started)
                await report(String(format: "%.0f s · %d inferences · %.2f /s · thermal %d · %d MB",
                                    now - started, count, rate, worstThermal.rawValue,
                                    residentMegabytes()))
            }
        }

        let elapsed = ProcessInfo.processInfo.systemUptime - started
        await report(String(format: "DONE %.0f s · %d inferences · %.2f /s · worst thermal %d · %d MB",
                            elapsed, count, Double(count) / elapsed, worstThermal.rawValue,
                            residentMegabytes()))
    }

    /// Resident footprint, reported alongside the rate. A number that climbs steadily
    /// rather than settling is the signature of the pool problem above coming back.
    private func residentMegabytes() -> Int {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? Int(info.resident_size / 1_048_576) : -1
    }

    @MainActor private func report(_ text: String) {
        line = text
        if text.hasPrefix("DONE") || text.hasPrefix("could not") { running = false }
    }
}
