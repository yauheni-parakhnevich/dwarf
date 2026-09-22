import SwiftUI

struct RootView: View {
    var body: some View {
        BenchmarkView()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
            .foregroundStyle(.white)
    }
}
