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
