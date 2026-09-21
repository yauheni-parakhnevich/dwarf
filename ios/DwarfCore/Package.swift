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
