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
    /// units, for the two to be considered the same animal, as of the moment the track
    /// was last actually seen. The gate actually applied to a given track widens with how
    /// long it has been since that moment; see `maxTrackSpeed`.
    public var gate: Double = 0.05
    /// How close another track's ground point must be, as a multiple of `gate`, before
    /// both are flagged `Track.isAmbiguous`. Wider than the association gate itself:
    /// two animals can be too close to trust their histories apart well before they are
    /// close enough for the tracker to actually merge them.
    public var ambiguityFactor: Double = 2.0
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
    /// Assumed worst-case cat speed, in frame widths per second, used to widen the
    /// association gate by how long it has been since a track was last actually seen. A
    /// fixed normalised gate silently means something different at every frame rate: at
    /// 3 fps a cat crossing the frame moves further between looks than a gate sized for
    /// 10 fps allows, and every detection would start a fresh, forever-unconfirmed
    /// track. 0.6 covers a cat moving faster than it plausibly will across a roughly 6 m
    /// wide frame, so a longer gap between looks trades a little association precision
    /// for not shattering a track under thermal throttling.
    public var maxTrackSpeed: Double = 0.6

    public init() {}
}

public struct Track: Equatable, Identifiable, Sendable {
    public let id: Int
    public var box: Rect
    public var confidence: Double
    public var lastSeen: TimeInterval
    public var isConfirmed: Bool
    public var isStill: Bool
    /// True when another live track's ground point is within `ambiguityFactor * gate` of
    /// this one. Nearest-neighbour association has no velocity or appearance model, so
    /// when two tracks are this close, association may already have swapped which
    /// history belongs to which animal — confirmation, stillness, and later a shot count
    /// cannot be trusted to belong to a single animal for either track. Whether to
    /// refuse to fire on an ambiguous track is a decision for the layer that fires, not
    /// this one.
    public var isAmbiguous: Bool

    /// Where the animal meets the ground: the aiming key.
    public var groundPoint: Point { box.bottomCenter }
    /// Roughly the head, used for aim beyond 4 m.
    public var headPoint: Point { box.topCenter }
}

/// What the detector has to say about one moment.
///
/// Detection runs outside this package and answers late, so most cycles carry no news at
/// all. The difference between "looked and saw nothing" and "has not answered yet" is not
/// cosmetic: a miss counts against `TrackerConfig.confirmHits`, so if every silent cycle
/// counted as a miss, a detector answering once every three cycles could never confirm a
/// cat it recognises perfectly every single time it actually looks.
public enum DetectorReport: Sendable {
    /// The detector answered for the frame captured at `capturedAt`, and an empty array is
    /// real evidence of absence. `capturedAt` is a monotonic uptime, and it is when the
    /// *frame* was taken rather than when the answer came back, so that a track's speed is
    /// measured over the interval the animal actually moved in.
    case answer(_ detections: [Detection], capturedAt: TimeInterval)
    /// Nothing has come back since the last cycle. Says nothing about any track.
    case pending
}

/// Turns per-frame detections into tracks with enough history to fire on.
public final class Tracker {
    public var config: TrackerConfig

    private struct State {
        var id: Int
        var box: Rect
        var confidence: Double
        /// The last time a detection was actually placed on this track (as opposed to a
        /// miss). Drives both `dropAfter` and how far `effectiveGate` widens.
        var lastSeen: TimeInterval
        /// The timestamp of the most recently recorded look, hit or miss. A second
        /// `update` call at this same timestamp — two crops from one scheduler cycle —
        /// merges into that look rather than adding a second, independent one; see
        /// `Tracker.apply`.
        var lastLookTime: TimeInterval
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

    public var tracks: [Track] { computeTracks() }

    /// Convenience for a detector answering in lockstep with the caller, which in practice
    /// means tests: the frame is assumed to have been captured at `time`.
    @discardableResult
    public func update(detections: [Detection], at time: TimeInterval) -> [Track] {
        update(.answer(detections, capturedAt: time), asOf: time)
    }

    /// - Parameters:
    ///   - report: what the detector has to say about this moment, if anything.
    ///   - now: the current monotonic uptime. Used only for ageing, so that a detector
    ///     which stops answering entirely still lets its tracks expire on the caller's
    ///     clock rather than freezing them alive forever.
    @discardableResult
    public func update(_ report: DetectorReport, asOf now: TimeInterval) -> [Track] {
        guard case .answer(let detections, let capturedAt) = report, capturedAt.isFinite else {
            // No answer came back. This moment is not evidence about anything, so every
            // look history is left exactly as it was; only ageing runs.
            for index in states.indices { trimSamples(&states[index], now: now) }
            states.removeAll { now - $0.lastSeen > config.dropAfter }
            return tracks
        }
        return associate(detections, capturedAt: capturedAt, asOf: now)
    }

    private func associate(_ detections: [Detection], capturedAt time: TimeInterval,
                           asOf now: TimeInterval) -> [Track] {
        var unmatched = Array(detections.indices)

        // Pass 1: greedy nearest-neighbour association against tracks that already
        // existed before this call. Each track claims its closest unmatched detection,
        // if any is within its (frame-rate-adjusted) gate. With at most a handful of
        // cats in a garden, anything cleverer than greedy nearest-neighbour is
        // unjustified complexity.
        for index in states.indices {
            let ground = states[index].box.bottomCenter
            let gate = effectiveGate(for: states[index], at: time)

            var bestSlot: Int?
            var bestDistance: Double?
            for (slot, detectionIndex) in unmatched.enumerated() {
                let distance = detections[detectionIndex].box.bottomCenter.distance(to: ground)
                guard distance <= gate else { continue }
                // Strict "<" so a tie is kept by the first candidate considered rather
                // than handed to whichever happens to sit later in the array.
                if bestDistance == nil || distance < bestDistance! {
                    bestDistance = distance
                    bestSlot = slot
                }
            }

            if let slot = bestSlot {
                let detection = detections[unmatched[slot]]
                unmatched.remove(at: slot)
                apply(detection, to: &states[index], at: time)
            } else if states[index].lastLookTime != time {
                // Seen nothing where this track was: that counts against confirmation —
                // but only once per moment. A second call at a timestamp this track was
                // already missed (or hit) at is a second crop of the same instant, not
                // fresh evidence of absence.
                record(look: false, in: &states[index])
                states[index].lastLookTime = time
            }

            trimSamples(&states[index], now: now)
        }

        // Pass 2: detections left over after pass 1 either belong to a track this same
        // call already touched or just created — overlapping crops of one animal — or
        // start a brand-new track. Checking against *all* current states, not only the
        // ones that existed before this call, stops two overlapping crops of one cat
        // from producing two tracks and doubling its shot budget later.
        for detectionIndex in unmatched {
            let detection = detections[detectionIndex]
            let ground = detection.box.bottomCenter

            var bestIndex: Int?
            var bestDistance: Double?
            for index in states.indices {
                let distance = states[index].box.bottomCenter.distance(to: ground)
                let gate = effectiveGate(for: states[index], at: time)
                guard distance <= gate else { continue }
                if bestDistance == nil || distance < bestDistance! {
                    bestDistance = distance
                    bestIndex = index
                }
            }

            if let index = bestIndex {
                apply(detection, to: &states[index], at: time)
                trimSamples(&states[index], now: now)
            } else {
                var state = State(id: nextID, box: detection.box, confidence: detection.confidence,
                                  lastSeen: time, lastLookTime: time)
                nextID += 1
                record(look: detection.confidence >= config.minConfidence, in: &state)
                state.samples.append((time, ground))
                states.append(state)
            }
        }

        states.removeAll { now - $0.lastSeen > config.dropAfter }
        return tracks
    }

    /// The distance below which a detection is considered the same animal as a track,
    /// widened by how long it has been since that track was last actually seen. See
    /// `TrackerConfig.maxTrackSpeed`.
    private func effectiveGate(for state: State, at time: TimeInterval) -> Double {
        config.gate + config.maxTrackSpeed * max(0, time - state.lastSeen)
    }

    /// Applies one matched detection to a track. A detection at a timestamp already
    /// recorded for this track — whether that record was a hit or only a miss — merges
    /// into that look instead of counting as a second, independent one: two crops of one
    /// scheduler cycle share a moment, not two separate looks at the animal.
    private func apply(_ detection: Detection, to state: inout State, at time: TimeInterval) {
        let momentAlreadyLogged = state.lastLookTime == time
        let momentAlreadyHit = state.lastSeen == time

        let confidence: Double
        let box: Rect
        if momentAlreadyHit, state.confidence >= detection.confidence {
            // A second, less confident crop of a moment already hit: keep the more
            // trustworthy box, but still fold in the (lower) confidence check below.
            confidence = state.confidence
            box = state.box
        } else {
            confidence = momentAlreadyHit ? max(state.confidence, detection.confidence) : detection.confidence
            box = detection.box
        }

        state.box = box
        state.confidence = confidence
        state.lastSeen = time
        state.lastLookTime = time

        let hit = confidence >= config.minConfidence
        if momentAlreadyLogged, !state.looks.isEmpty {
            state.looks[state.looks.count - 1] = hit
        } else {
            record(look: hit, in: &state)
        }

        let groundPoint = box.bottomCenter
        if momentAlreadyLogged, let lastSample = state.samples.last, lastSample.time == time {
            state.samples[state.samples.count - 1] = (time, groundPoint)
        } else {
            state.samples.append((time, groundPoint))
        }
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

    private func computeTracks() -> [Track] {
        let grounds = states.map { $0.box.bottomCenter }
        let ambiguityDistance = config.gate * config.ambiguityFactor
        return states.indices.map { i in
            let ambiguous = states.indices.contains { j in
                j != i && grounds[i].distance(to: grounds[j]) <= ambiguityDistance
            }
            return track(from: states[i], isAmbiguous: ambiguous)
        }
    }

    private func track(from state: State, isAmbiguous: Bool) -> Track {
        Track(
            id: state.id,
            box: state.box,
            confidence: state.confidence,
            lastSeen: state.lastSeen,
            isConfirmed: state.looks.filter { $0 }.count >= config.confirmHits,
            isStill: isStill(state),
            isAmbiguous: isAmbiguous
        )
    }

    /// Still means: a full window of history exists, and the animal covered almost no
    /// ground across it. Measured as total path length over elapsed time, not the
    /// distance between the first and last sample: a cat that walks out and back within
    /// the window — or paces side to side — has covered real ground even though it ends
    /// up near where it started, and the endpoint distance would miss that entirely.
    /// Path length is strictly more conservative than the endpoint measure — any path
    /// that reads as still by path length also reads as still by endpoints, since the
    /// endpoint distance can never exceed the path length — so a genuinely stationary
    /// cat is unaffected. Demanding the full window stops a brand-new track from being
    /// declared still simply because it has only one sample.
    private func isStill(_ state: State) -> Bool {
        guard state.samples.count >= 2 else { return false }
        let first = state.samples[0]
        let last = state.samples[state.samples.count - 1]
        let elapsed = last.time - first.time
        guard elapsed >= config.stillWindow * 0.8 else { return false }

        var pathLength = 0.0
        for i in 1..<state.samples.count {
            pathLength += state.samples[i].point.distance(to: state.samples[i - 1].point)
        }
        return pathLength / elapsed <= config.stillSpeed
    }
}
