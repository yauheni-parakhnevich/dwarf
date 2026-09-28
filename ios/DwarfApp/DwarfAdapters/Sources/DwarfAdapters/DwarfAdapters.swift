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
