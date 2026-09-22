import SwiftUI
import DwarfCore
import DwarfAdapters

/// The gnome's own screen: a live view of what it sees, and every number needed to tell a
/// quiet garden from a broken gnome.
///
/// Weighted towards diagnosis rather than reassurance. A gnome that is tracking, connected
/// and calibrated can still be useless — looking the wrong way up, cutting crops from the
/// wrong part of the frame, aiming with a calibration fitted before the phone was moved, or
/// refusing every shot for a reason it never says out loud. Each of those has a line here.
struct RootView: View {
    @StateObject private var gnome = GnomeController()

    var body: some View {
        // Side by side when there is width for it, stacked when there is not. The phone
        // may end up either way up in the gnome, and the diagnostics are no use in a
        // column two words wide.
        GeometryReader { geometry in
            if geometry.size.width >= geometry.size.height {
                HStack(spacing: 0) { pane }
            } else {
                VStack(spacing: 0) { pane }
            }
        }
        .background(Color.black)
        .foregroundStyle(.white)
        .onAppear { gnome.start() }
    }

    @ViewBuilder private var pane: some View {
        Group {
            preview
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.black)

            Divider().overlay(Color.white.opacity(0.2))

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    verdict
                    Group {
                        panel("SEEING", seeing)
                        panel("PIPELINE", pipeline)
                        panel("GNOME", device)
                        panel("SETUP", setup)
                    }
                    mountControl
                    modePicker
                }
                .padding(12)
            }
            .frame(maxWidth: 340)
        }
    }

    // MARK: the picture

    /// Blobs, crops and tracks drawn in normalised frame coordinates. This one view exposes
    /// what no counter can: whether the image is the right way up, whether crops are being
    /// cut where the motion actually is, and whether a box sits on the animal or beside it.
    /// The largest box of the frame's own shape that fits the space offered.
    ///
    /// Computed here rather than left to `.aspectRatio`, which was applied outside a
    /// `GeometryReader` and stopped constraining anything once the layout learned to stack
    /// for a portrait screen. The preview layer uses `.resize`, so it fills whatever box it
    /// is given without regard to the video's own shape — hand it a box of the wrong
    /// proportions and the picture is simply squashed, which is what happened. The overlay
    /// shares the same box, so normalised coordinates still land where the pipeline says.
    private func fitted(_ available: CGSize) -> CGSize {
        let aspect = gnome.frameAspect
        guard available.width > 0, available.height > 0, aspect > 0 else { return .zero }
        return available.width / available.height > aspect
            ? CGSize(width: available.height * aspect, height: available.height)
            : CGSize(width: available.width, height: available.width / aspect)
    }

    private var preview: some View {
        GeometryReader { geometry in
            let picture = fitted(geometry.size)
            let w = picture.width, h = picture.height
            ZStack(alignment: .topLeading) {
                Color.black

                // The picture the overlay is drawn on, turned by the same quarter turns
                // FrameGeometry applies so the two agree by construction. `.resize` rather
                // than an aspect-preserving gravity: the container is already the frame's
                // own aspect ratio, so normalised coordinates map straight to it and a box
                // lands exactly where the pipeline thinks the animal is.
                // Sized to the frame's own shape *before* the turn, so a quarter turn puts
                // a 16:9 picture into a 9:16 box rather than squashing it into one.
                CameraPreview(session: gnome.session)
                    .frame(width: gnome.quarterTurns % 2 == 0 ? w : h,
                           height: gnome.quarterTurns % 2 == 0 ? h : w)
                    .rotationEffect(.degrees(Double(gnome.quarterTurns) * 90))
                    .frame(width: w, height: h)
                    .clipped()

                ForEach(Array(gnome.snapshot.blobs.enumerated()), id: \.offset) { _, blob in
                    box(blob.boundingBox, w, h).stroke(Color.gray.opacity(0.6), lineWidth: 1)
                }
                ForEach(Array(gnome.snapshot.cropRequests.enumerated()), id: \.offset) { _, crop in
                    box(crop.rect, w, h)
                        .stroke(crop.kind == .sweep ? Color.blue.opacity(0.5) : Color.teal,
                                style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                }
                ForEach(gnome.snapshot.tracks, id: \.id) { track in
                    let fireable = gnome.snapshot.refusal == nil
                    box(track.box, w, h)
                        .stroke(track.isConfirmed ? (fireable ? Color.green : Color.yellow) : Color.orange,
                                lineWidth: 2)
                    // Where the gnome believes the animal meets the ground, which is the
                    // point every aim is computed from. If these sit on a cat's back, the
                    // mount's quarter turns are wrong.
                    Circle()
                        .fill(Color.red)
                        .frame(width: 6, height: 6)
                        .position(x: track.groundPoint.x * w, y: track.groundPoint.y * h)
                }

                if gnome.snapshot.paused {
                    Text("PAUSED").font(.caption.bold()).foregroundStyle(.orange).padding(6)
                }
            }
            .frame(width: w, height: h)
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
    }

    private func box(_ rect: Rect, _ w: CGFloat, _ h: CGFloat) -> Path {
        Path(CGRect(x: rect.x * w, y: rect.y * h, width: rect.width * w, height: rect.height * h))
    }

    // MARK: the words

    private var verdict: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(headline).font(.system(.title3, design: .monospaced).bold())
            Text(subhead).font(.caption).foregroundStyle(.secondary)
        }
    }

    private var headline: String {
        if gnome.modelMissing { return "NO MODEL" }
        switch gnome.snapshot.decision {
        case .none: return gnome.snapshot.tracks.isEmpty ? "watching" : "holding"
        case .aim(let pan, let tilt): return String(format: "aim %.1f° %.1f°", pan, tilt)
        case .park: return "parked"
        case .shoot(_, _, let ms): return "SHOT \(ms) ms"
        case .wouldShoot(_, _, let ms): return "would shoot \(ms) ms"
        }
    }

    /// The question an owner actually asks, answered.
    private var subhead: String {
        if gnome.modelMissing { return "nothing is being detected" }
        if !gnome.calibrated { return "not calibrated — cannot aim" }
        guard let refusal = gnome.snapshot.refusal else {
            return gnome.snapshot.tracks.isEmpty ? "nothing in the garden" : "ready to fire"
        }
        switch refusal {
        case .notOperating:      return "not operating"
        case .notConfirmed:      return "not confirmed yet"
        case .notStill:          return "moving"
        case .ambiguous:         return "two animals too close to tell apart"
        case .aimFlagged:        return "aim cannot be trusted here"
        case .tooClose:          return "closer than 2 m"
        case .noFireZone:        return "standing in a no-fire zone"
        case .noFreshStatus:     return "no fresh word from the gnome"
        case .deviceNotReady:    return "gnome not ready (armed? tank? fault?)"
        case .animalCapReached:  return "this animal has had enough"
        case .hourlyCapReached:  return "hourly limit reached"
        case .animalCoolingDown: return "cooling down after the last shot"
        case .nozzleCoolingDown: return "nozzle cooling down"
        case .noAimSolution:     return "no aim solution"
        }
    }

    private var seeing: [(String, String)] {
        let s = gnome.snapshot
        return [
            ("tracks", "\(s.tracks.count)"),
            ("blobs", "\(s.blobs.count)"),
            ("luma", s.lumaUnusable ? "unusable" : String(format: "%.0f", s.meanLuma)),
            ("range", s.solutions.values.first.map { String(format: "%.1f m", $0.rangeM) } ?? "—")
        ]
    }

    private var pipeline: [(String, String)] {
        let s = gnome.snapshot
        return [
            ("camera", describe(gnome.camera)),
            ("fps", String(format: "%.1f / %.0f asked", s.framesPerSecond, gnome.frameRate)),
            ("answers/s", String(format: "%.1f", s.answersPerSecond)),
            ("dropped", "\(s.droppedRequests)"),
            ("model fails", "\(s.detectorFailures)"),
            ("detector", s.detectorBusySince.map { String(format: "busy since %.1f", $0) } ?? "idle"),
            ("rate", s.cycleDivisor > 1 ? "halved (heat)" : "full"),
            ("clock", s.clockAnomalies == 0 ? "steady" : "\(s.clockAnomalies) jumps")
        ]
    }

    private var device: [(String, String)] {
        let s = gnome.snapshot
        guard let status = s.status else {
            if gnome.needsPairing {
                // Distinct from "down" on purpose: the gnome is right there, refusing every
                // command until the phone bonds with it. See BluetoothTransport.needsPairing.
                return [("link", "needs pairing — enter the passkey from the gnome's serial console")]
            }
            return [("link", gnome.linkUp ? "up, but silent" : "down")]
        }
        return [
            ("link", "up"),
            ("armed", status.armed ? "yes" : "no"),
            ("tank", status.tankOk ? "ok" : "EMPTY"),
            ("fault", status.fault.map { "\($0)" } ?? "none"),
            ("inside", String(format: "%.1f °C", status.temp)),
            ("shots", "\(status.shots) · \(s.shotsThisHour) this hour"),
            ("send fails", "\(s.sendFailures)"),
            ("refused", s.deviceRefusals.isEmpty ? "none"
                : s.deviceRefusals.map { "\($0.key) \($0.value)" }.sorted().joined(separator: " "))
        ]
    }

    private var setup: [(String, String)] {
        [
            ("calibration", gnome.calibrated ? "\(gnome.calibrationPoints) points" : "NONE"),
            ("no-fire zones", gnome.noFireZones == 0 ? "NONE" : "\(gnome.noFireZones)"),
            ("files", gnome.loadFailures.isEmpty ? "ok" : gnome.loadFailures.joined(separator: " "))
        ]
    }

    private func describe(_ health: CameraSource.Health) -> String {
        switch health {
        case .stopped: return "stopped"
        case .running: return "running"
        case .interrupted(let why): return "interrupted \(why)"
        case .failed(let why): return "FAILED \(why)"
        case .denied: return "PERMISSION DENIED"
        }
    }

    private func panel(_ title: String, _ rows: [(String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption2.bold()).foregroundStyle(.secondary)
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack {
                    Text(row.0).foregroundStyle(.secondary)
                    Spacer()
                    Text(row.1)
                }
                .font(.caption.monospaced())
            }
        }
    }

    /// The mount's orientation, which only a person looking at the screen can settle.
    private var mountControl: some View {
        HStack {
            Text("mount").font(.caption2.bold()).foregroundStyle(.secondary)
            Spacer()
            Button {
                gnome.rotate()
            } label: {
                Label("\(gnome.quarterTurns * 90)°", systemImage: "rotate.right")
                    .font(.caption.monospaced())
            }
            .buttonStyle(.bordered)
        }
    }

    private var modePicker: some View {
        Picker("mode", selection: Binding(get: { gnome.mode }, set: { gnome.set(mode: $0) })) {
            Text("off").tag(Mode.disarmed)
            Text("dry").tag(Mode.dryRun)
            Text("live").tag(Mode.live)
        }
        .pickerStyle(.segmented)
    }
}
