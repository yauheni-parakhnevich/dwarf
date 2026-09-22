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
