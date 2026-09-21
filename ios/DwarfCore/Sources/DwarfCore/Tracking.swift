import Foundation

/// One box the detector returned for one crop. Only cats reach here: the iOS layer filters
/// the model's classes before calling in.
public struct Detection: Equatable, Sendable {
    public let box: Rect
    public let confidence: Double

    public init(box: Rect, confidence: Double) {
        self.box = box
        self.confidence = confidence
    }
}

public struct TrackerConfig: Equatable, Sendable {
    /// Maximum distance between a track's ground point and a detection's, in normalised
    /// units, for the two to be considered the same animal.
    public var gate: Double = 0.05
    /// A track is confirmed at `confirmHits` positive looks out of the last `confirmWindow`.
    public var confirmHits: Int = 2
    public var confirmWindow: Int = 3
    /// Detections below this confidence do not count as a positive look.
    public var minConfidence: Double = 0.5
    /// Speed below which a track counts as still, in frame widths per second.
    public var stillSpeed: Double = 0.02
    /// How far back stillness is measured.
    public var stillWindow: TimeInterval = 1.0
    /// A track unseen for this long is forgotten.
    public var dropAfter: TimeInterval = 3.0

    public init() {}
}

public struct Track: Equatable, Identifiable, Sendable {
    public let id: Int
    public var box: Rect
    public var confidence: Double
    public var lastSeen: TimeInterval
    public var isConfirmed: Bool
    public var isStill: Bool

    /// Where the animal meets the ground: the aiming key.
    public var groundPoint: Point { box.bottomCenter }
    /// Roughly the head, used for aim beyond 4 m.
    public var headPoint: Point { box.topCenter }
}

/// Turns per-frame detections into tracks with enough history to fire on.
public final class Tracker {
    public var config: TrackerConfig

    private struct State {
        var id: Int
        var box: Rect
        var confidence: Double
        var lastSeen: TimeInterval
        /// Recent looks, newest last: true when the detector saw a confident cat.
        var looks: [Bool] = []
        /// Recent ground positions for the stillness test, newest last.
        var samples: [(time: TimeInterval, point: Point)] = []
    }

    private var states: [State] = []
    private var nextID = 1

    public init(config: TrackerConfig = TrackerConfig()) {
        self.config = config
    }

    public var tracks: [Track] { states.map(track(from:)) }

    public func update(detections: [Detection], at time: TimeInterval) -> [Track] {
        var unmatched = Array(detections.indices)

        // Greedy nearest-neighbour association. With at most a handful of cats in a
        // garden, anything cleverer is unjustified complexity.
        for index in states.indices {
            let ground = states[index].box.bottomCenter
            var bestSlot: Int?
            var bestDistance = config.gate

            for (slot, detectionIndex) in unmatched.enumerated() {
                let distance = detections[detectionIndex].box.bottomCenter.distance(to: ground)
                if distance <= bestDistance {
                    bestDistance = distance
                    bestSlot = slot
                }
            }

            if let slot = bestSlot {
                let detection = detections[unmatched[slot]]
                unmatched.remove(at: slot)
                states[index].box = detection.box
                states[index].confidence = detection.confidence
                states[index].lastSeen = time
                record(look: detection.confidence >= config.minConfidence, in: &states[index])
                states[index].samples.append((time, detection.box.bottomCenter))
            } else {
                // Seen nothing where this track was: that counts against confirmation.
                record(look: false, in: &states[index])
            }

            trimSamples(&states[index], now: time)
        }

        for detectionIndex in unmatched {
            let detection = detections[detectionIndex]
            var state = State(id: nextID, box: detection.box,
                              confidence: detection.confidence, lastSeen: time)
            nextID += 1
            record(look: detection.confidence >= config.minConfidence, in: &state)
            state.samples.append((time, detection.box.bottomCenter))
            states.append(state)
        }

        states.removeAll { time - $0.lastSeen > config.dropAfter }
        return tracks
    }

    private func record(look: Bool, in state: inout State) {
        state.looks.append(look)
        if state.looks.count > config.confirmWindow {
            state.looks.removeFirst(state.looks.count - config.confirmWindow)
        }
    }

    private func trimSamples(_ state: inout State, now: TimeInterval) {
        state.samples.removeAll { now - $0.time > config.stillWindow }
    }

    private func track(from state: State) -> Track {
        Track(
            id: state.id,
            box: state.box,
            confidence: state.confidence,
            lastSeen: state.lastSeen,
            isConfirmed: state.looks.filter { $0 }.count >= config.confirmHits,
            isStill: isStill(state)
        )
    }

    /// Still means: a full window of history exists, and the animal covered almost no
    /// ground across it. Demanding the full window stops a brand-new track from being
    /// declared still simply because it has only one sample.
    private func isStill(_ state: State) -> Bool {
        guard let first = state.samples.first, let last = state.samples.last else { return false }
        let elapsed = last.time - first.time
        guard elapsed >= config.stillWindow * 0.8 else { return false }
        return last.point.distance(to: first.point) / elapsed <= config.stillSpeed
    }
}
