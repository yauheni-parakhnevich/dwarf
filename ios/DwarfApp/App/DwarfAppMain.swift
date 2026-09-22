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
