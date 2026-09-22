import Foundation
import CoreBluetooth
import DwarfAdapters

/// The phone's side of the link.
///
/// Scans for the gnome's service, connects, subscribes to status notifications and writes
/// commands. Reconnection is automatic and quiet: a gnome that drops out for a moment
/// should not need anyone's attention, and `ActuatorLink` already refuses to offer a stale
/// status while it is away.
///
/// Deliberately thin, on purpose: everything here can only be exercised against a real
/// radio, so the only logic that belongs here is CoreBluetooth plumbing. The one genuinely
/// testable piece — telling "no gnome found" apart from "the gnome is there and refusing us
/// for want of a bond" — is `PairingTracker`, over in `DwarfAdapters`, which this class only
/// ever *drives* from the delegate callbacks below.
///
/// Both `cmd` and `status` now require an authenticated, encrypted link (bonding with LE
/// Secure Connections and a passkey — see the BLE access-control comment block in
/// `firmware/src/main.cpp`). The first write or subscription attempt on an unbonded link
/// triggers iOS's own pairing UI; there is no API to drive that dialog from code and none is
/// wanted. Until bonding completes, writes fail with `CBATTError.insufficientAuthentication`
/// or `.insufficientEncryption` — a state distinct from "not connected", and exposed here as
/// `needsPairing` for exactly that reason.
public final class BluetoothTransport: NSObject, Transport {
    public static let service = CBUUID(string: "EC61AB6F-D20E-4217-93F9-4A3DF81B75D3")
    public static let commandCharacteristic = CBUUID(string: "7C7FBA40-4383-4738-AD6B-09986229ED6A")
    public static let statusCharacteristic = CBUUID(string: "6DF54A5A-41DC-4414-AB6A-1354C959CF0A")

    /// One JSON object per write; the spec caps a message at 180 bytes.
    public let framing: Framing = .perWrite

    /// Called with whatever arrived, in whatever sized pieces it arrived in. Fired outside
    /// `lock`, never from inside it — see the note on `lock` below.
    public var onReceive: ((Data) -> Void)?
    /// Called when the link comes up or goes down. Also fired outside `lock`.
    public var onConnectionChange: ((Bool) -> Void)?

    // MARK: - State shared between CoreBluetooth's queue and whatever queue asks

    /// CoreBluetooth delivers every delegate callback on `cbQueue`, below — never on the
    /// queue that calls `send(_:)` or reads `isConnected`/`needsPairing`. `ActuatorLink`
    /// reads `isConnected` from the main actor, `send`s from wherever the app's command path
    /// runs, and CoreBluetooth writes `connected`/`peripheral`/`writeCharacteristic` from its
    /// own queue: three parties, no shared ownership, unless something says otherwise. This
    /// lock is that something. This project has already had ThreadSanitizer find real races
    /// in two other types built this way (one of them a segfault) — both went unnoticed
    /// until something actually drove the racing side. `FakeTransport` never drives this
    /// one; a real radio does, on every callback, for as long as the app runs.
    private let lock = NSLock()
    private var connected = false
    private var peripheral: CBPeripheral?
    private var writeCharacteristic: CBCharacteristic?
    private let pairing = PairingTracker()

    public var isConnected: Bool { withLock { connected } }

    /// True while the gnome is in range but has refused every write or subscription for
    /// want of a bond. See `PairingTracker` for the rules this follows.
    public var needsPairing: Bool { withLock { pairing.needsPairing } }

    /// A dedicated serial queue, not `.global(qos:)`. A concurrent queue does not promise
    /// CoreBluetooth's callbacks run one at a time or in the order the radio produced them —
    /// only that each one eventually runs on it — and this class already has to reason about
    /// callbacks racing `send`/`isConnected` from other queues; there is no reason to also
    /// let two callbacks race each other.
    private let cbQueue = DispatchQueue(label: "garden.dwarf.ble", qos: .userInitiated)
    private var central: CBCentralManager!
    /// Remembered across launches so a reconnect does not need a fresh scan. CoreBluetooth
    /// never exposes a peripheral's BLE address to an app — it hands back an opaque per-app
    /// identifier instead — so this is the only handle worth keeping.
    private var knownIdentifier: UUID? {
        get { UserDefaults.standard.string(forKey: "gnome.peripheral").flatMap(UUID.init) }
        set { UserDefaults.standard.set(newValue?.uuidString, forKey: "gnome.peripheral") }
    }

    public override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: cbQueue)
    }

    public func send(_ data: Data) throws {
        let ready: (CBPeripheral, CBCharacteristic)? = withLock {
            guard connected, let peripheral, let writeCharacteristic else { return nil }
            return (peripheral, writeCharacteristic)
        }
        guard let (peripheral, characteristic) = ready else { throw TransportError.notConnected }
        // With response, deliberately. Write-without-response is faster and silently drops
        // under congestion, and a dropped `park` leaves the head where it was. The
        // asynchronous outcome — including a rejection for want of a bond — arrives later in
        // `peripheral(_:didWriteValueFor:error:)`, not here: this only reports whether the
        // write could be *attempted*, exactly like every other `Transport`.
        peripheral.writeValue(data, for: characteristic, type: .withResponse)
    }

    private func withLock<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    /// Same source `DwarfAdapters.SystemClock` uses. Not worth injecting a `Clock` here for
    /// it: this value only ever feeds `PairingTracker`'s "did this disconnect happen
    /// suspiciously soon after connecting" heuristic, which — like everything else in this
    /// class — cannot be exercised without a radio regardless of where the number comes from.
    private func uptime() -> TimeInterval { ProcessInfo.processInfo.systemUptime }

    // MARK: - Scanning and connecting

    private func beginScanning() {
        guard central.state == .poweredOn else { return }
        if let identifier = knownIdentifier,
           let known = central.retrievePeripherals(withIdentifiers: [identifier]).first {
            connect(known)
            return
        }
        // No timeout, no backoff: the gnome is unattended, and a phone that needs restarting
        // to find it again is a failure. `CBCentralManagerScanOptionAllowDuplicatesKey`
        // defaults to false, so the radio itself coalesces repeat adverts rather than waking
        // this process for each one.
        central.scanForPeripherals(withServices: [BluetoothTransport.service])
    }

    private func connect(_ peripheral: CBPeripheral) {
        withLock { self.peripheral = peripheral }
        peripheral.delegate = self
        central.stopScan()
        central.connect(peripheral)
    }
}

extension BluetoothTransport: CBCentralManagerDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn {
            beginScanning()
            return
        }
        // Off, unauthorised, unsupported or resetting says nothing about pairing either way
        // — only a real disconnect or a real GATT error does — so this only tears down the
        // radio-level state, the same as an ordinary disconnect, and leaves `needsPairing`
        // exactly as `PairingTracker.disconnected` would.
        let wasConnected = withLock { () -> Bool in
            pairing.disconnected(atUptime: uptime())
            peripheral = nil
            writeCharacteristic = nil
            let was = connected
            connected = false
            return was
        }
        if wasConnected { onConnectionChange?(false) }
    }

    public func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                               advertisementData: [String: Any], rssi RSSI: NSNumber) {
        // Ignore discoveries once a peripheral is already being connected to or is
        // connected: two gnomes in range, or a stranger's device advertising the same
        // service UUID, must not make the app flip its target mid-connection.
        let alreadyTargeting = withLock { self.peripheral != nil }
        guard !alreadyTargeting else { return }
        // And once we know which identifier we bonded with, a look-alike that happens to
        // answer first is not it — wait for the real one rather than switching targets.
        if let known = knownIdentifier, known != peripheral.identifier { return }

        knownIdentifier = peripheral.identifier
        connect(peripheral)
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        withLock { pairing.connected(atUptime: uptime()) }
        peripheral.discoverServices([BluetoothTransport.service])
    }

    public func centralManager(_ central: CBCentralManager,
                               didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        let wasConnected = withLock { () -> Bool in
            pairing.disconnected(atUptime: uptime())
            self.peripheral = nil
            writeCharacteristic = nil
            let was = connected
            connected = false
            return was
        }
        if wasConnected { onConnectionChange?(false) }
        // The gnome is unattended and its firmware restarts advertising the instant it sees
        // this disconnect (`ServerCallbacks::onDisconnect`). Nobody is here to relaunch the
        // app, so this side has to be just as quick to look again.
        beginScanning()
    }

    public func centralManager(_ central: CBCentralManager,
                               didFailToConnect peripheral: CBPeripheral, error: Error?) {
        // No `pairing.disconnected` here: `didConnect` never fired for this attempt, so
        // `PairingTracker` never recorded it as connected in the first place.
        withLock {
            self.peripheral = nil
            writeCharacteristic = nil
            connected = false
        }
        beginScanning()
    }
}

extension BluetoothTransport: CBPeripheralDelegate {
    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard let service = peripheral.services?.first(where: { $0.uuid == BluetoothTransport.service })
        else { return }
        peripheral.discoverCharacteristics(
            [BluetoothTransport.commandCharacteristic, BluetoothTransport.statusCharacteristic],
            for: service)
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                           error: Error?) {
        var writeChar: CBCharacteristic?
        for characteristic in service.characteristics ?? [] {
            switch characteristic.uuid {
            case BluetoothTransport.commandCharacteristic:
                writeChar = characteristic
            case BluetoothTransport.statusCharacteristic:
                peripheral.setNotifyValue(true, for: characteristic)
            default:
                break
            }
        }
        // Connected means "able to attempt a command", not "the radio is bonded" — until the
        // command characteristic exists there is nothing to write to, and until the first
        // write is attempted there is no way to learn whether we are bonded at all. See
        // `send(_:)` and `PairingTracker`.
        let becameConnected: Bool? = withLock {
            writeCharacteristic = writeChar
            let newValue = writeChar != nil
            guard newValue != connected else { return nil }
            connected = newValue
            return newValue
        }
        if let becameConnected { onConnectionChange?(becameConnected) }
    }

    public func peripheral(_ peripheral: CBPeripheral,
                           didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard characteristic.uuid == BluetoothTransport.statusCharacteristic,
              isAuthenticationError(error) else { return }
        withLock { pairing.authenticationFailed() }
    }

    public func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard characteristic.uuid == BluetoothTransport.commandCharacteristic else { return }
        withLock {
            if isAuthenticationError(error) {
                pairing.authenticationFailed()
            } else if error == nil {
                pairing.authenticationSucceeded()
            }
            // Any other error (the link dropping mid-write, say) says nothing about pairing
            // either way, so it is left alone here. It is also not counted anywhere as a
            // send failure: `Runtime.sendFailures` only ever sees `send(_:)`'s synchronous
            // throw, and this callback arrives after `send(_:)` has already returned
            // successfully. A write that is accepted here and rejected by the radio a moment
            // later is a real, unfixed gap — see the write-up.
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard characteristic.uuid == BluetoothTransport.statusCharacteristic,
              let value = characteristic.value else { return }
        // A notification arriving at all is only possible over an encrypted, authenticated
        // link — NimBLE's notify() silently skips any subscriber that is not — so this is as
        // much proof of a working bond as a successful write is.
        withLock { pairing.authenticationSucceeded() }
        onReceive?(value)
    }

    private func isAuthenticationError(_ error: Error?) -> Bool {
        guard let attError = error as? CBATTError else { return false }
        switch attError.code {
        case .insufficientAuthentication, .insufficientEncryption:
            return true
        default:
            return false
        }
    }
}
