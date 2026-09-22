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

            if !gnome.health.isEmpty {
                Text(gnome.health)
                    .font(.caption.monospaced())
                    .foregroundStyle(.orange)
            }

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
