// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DwarfAdapters",
    platforms: [.macOS(.v13), .iOS(.v15)],
    products: [
        .library(name: "DwarfAdapters", targets: ["DwarfAdapters"])
    ],
    dependencies: [
        .package(path: "../../DwarfCore")
    ],
    targets: [
        .target(name: "DwarfAdapters", dependencies: [
            .product(name: "DwarfCore", package: "DwarfCore")
        ]),
        .testTarget(name: "DwarfAdaptersTests", dependencies: ["DwarfAdapters"])
    ]
)
