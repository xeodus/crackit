import AppKit
import AVFoundation
import ScreenCaptureKit
import CoreMedia

func emit(_ object: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
       let text = String(data: data, encoding: .utf8) { print(text) }
}

func convertAudio(_ input: String, _ output: String) throws {
    let source = try AVAudioFile(forReading: URL(fileURLWithPath: input))
    guard source.length > 0, source.length < 20_000_000,
          let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true),
          let converter = AVAudioConverter(from: source.processingFormat, to: target),
          let inputBuffer = AVAudioPCMBuffer(pcmFormat: source.processingFormat, frameCapacity: AVAudioFrameCount(source.length)) else {
        throw NSError(domain: "Crackit", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unsupported or oversized audio file"])
    }
    try source.read(into: inputBuffer)
    let frames = AVAudioFrameCount(ceil(Double(inputBuffer.frameLength) * 16000 / source.processingFormat.sampleRate) + 4096)
    guard let converted = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: frames) else {
        throw NSError(domain: "Crackit", code: 2)
    }
    var consumed = false
    var conversionError: NSError?
    let status = converter.convert(to: converted, error: &conversionError) { _, state in
        if consumed { state.pointee = .endOfStream; return nil }
        consumed = true; state.pointee = .haveData; return inputBuffer
    }
    if let conversionError = conversionError { throw conversionError }
    guard status != .error, converted.frameLength > 0 else { throw NSError(domain: "Crackit", code: 3) }
    let destination = try AVAudioFile(forWriting: URL(fileURLWithPath: output), settings: target.settings,
                                    commonFormat: .pcmFormatInt16, interleaved: true)
    try destination.write(from: converted)
    emit(["kind": "controlled_audio_conversion", "sample_rate": 16000, "channels": 1,
          "sample_width_bytes": 2, "frames": converted.frameLength,
          "duration_seconds": Double(converted.frameLength) / 16000])
}

struct SourceMetrics {
    var buffers = 0
    var samples: Int64 = 0
    var sampleRate = 0.0
    var channels: UInt32 = 0
    var firstPTS: Double?
    var lastPTS: Double?
    var expectedPTS: Double?
    var gaps = 0
    var discontinuities = 0
    var peakRMS = 0.0
    var rmsMeasuredBuffers = 0
    var formatFlags: UInt32 = 0
    var bitsPerChannel: UInt32 = 0
    var lastArrival: Double?
    var firstArrival: Double?
    var invalidBuffers = 0
    func report(now: Double) -> [String: Any] {
        var data: [String: Any] = ["buffers": buffers, "samples": samples,
            "sample_rate": sampleRate, "channels": channels, "gaps_over_100ms": gaps,
            "backwards_timestamps": discontinuities, "peak_rms": peakRMS,
            "invalid_buffers": invalidBuffers]
        data["rms_measured_buffers"] = rmsMeasuredBuffers
        data["format_flags"] = formatFlags
        data["bits_per_channel"] = bitsPerChannel
        if let firstPTS = firstPTS { data["first_pts_seconds"] = firstPTS }
        if let lastPTS = lastPTS { data["last_pts_seconds"] = lastPTS }
        if let lastArrival = lastArrival { data["last_buffer_age_ms"] = (now - lastArrival) * 1000 }
        if let firstArrival = firstArrival { data["first_arrival_monotonic_seconds"] = firstArrival }
        return data
    }
}

final class CaptureProbe: NSObject, SCStreamOutput, SCStreamDelegate {
    private let lock = NSLock()
    private var metrics: [String: SourceMetrics] = [:]
    private var errors: [String] = []
    private var activeStream: SCStream?
    private var startedAt = 0.0
    private(set) var running = false
    var onUnexpectedStop: (() -> Void)?

    func start(microphone: Bool) async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else { throw NSError(domain: "Crackit", code: 4, userInfo: [NSLocalizedDescriptionKey: "No capture display available"] ) }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let configuration = SCStreamConfiguration()
        configuration.width = 2; configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        configuration.queueDepth = 3
        configuration.capturesAudio = true
        configuration.captureMicrophone = microphone
        configuration.excludesCurrentProcessAudio = false
        configuration.sampleRate = 48000; configuration.channelCount = 1
        configuration.showsCursor = false
        let stream = SCStream(filter: filter, configuration: configuration, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: DispatchQueue(label: "dev.crackit.system"))
        if microphone {
            try stream.addStreamOutput(self, type: .microphone, sampleHandlerQueue: DispatchQueue(label: "dev.crackit.microphone"))
        }
        lock.withLock {
            metrics = ["system": SourceMetrics()]
            if microphone { metrics["mic"] = SourceMetrics() }
            errors = []; startedAt = ProcessInfo.processInfo.systemUptime
        }
        activeStream = stream
        try await stream.startCapture()
        running = true
    }

    func stop() async {
        if let stream = activeStream {
            do { try await stream.stopCapture() } catch {
                lock.withLock { errors.append("Stop failed: " + error.localizedDescription) }
            }
        }
        activeStream = nil; running = false
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        lock.lock(); errors.append(error.localizedDescription); lock.unlock()
        DispatchQueue.main.async { [weak self] in
            self?.running = false; self?.onUnexpectedStop?()
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer buffer: CMSampleBuffer, of type: SCStreamOutputType) {
        let source = type == .microphone ? "mic" : "system"
        lock.lock(); defer { lock.unlock() }
        var value = metrics[source] ?? SourceMetrics()
        guard buffer.isValid, CMSampleBufferDataIsReady(buffer),
              let description = CMSampleBufferGetFormatDescription(buffer),
              let format = CMAudioFormatDescriptionGetStreamBasicDescription(description) else {
            value.invalidBuffers += 1; metrics[source] = value; return
        }
        let pts = CMSampleBufferGetPresentationTimeStamp(buffer).seconds
        let samples = CMSampleBufferGetNumSamples(buffer)
        guard pts.isFinite, format.pointee.mSampleRate > 0 else {
            value.invalidBuffers += 1; metrics[source] = value; return
        }
        let now = ProcessInfo.processInfo.systemUptime
        value.buffers += 1; value.samples += Int64(samples)
        value.sampleRate = format.pointee.mSampleRate; value.channels = format.pointee.mChannelsPerFrame
        value.formatFlags = format.pointee.mFormatFlags
        value.bitsPerChannel = format.pointee.mBitsPerChannel
        if value.firstPTS == nil { value.firstPTS = pts; value.firstArrival = now }
        if let expected = value.expectedPTS {
            if pts - expected > 0.1 { value.gaps += 1 }
            if pts < expected - 0.02 { value.discontinuities += 1 }
        }
        value.lastPTS = pts; value.expectedPTS = pts + Double(samples) / value.sampleRate
        value.lastArrival = now
        if format.pointee.mFormatFlags & kAudioFormatFlagIsFloat != 0,
           format.pointee.mBitsPerChannel == 32, let block = CMSampleBufferGetDataBuffer(buffer) {
            let length = CMBlockBufferGetDataLength(block)
            if length > 0 && length < 1_000_000 {
                var data = Data(count: length)
                let copyResult = data.withUnsafeMutableBytes { raw in
                    CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: length, destination: raw.baseAddress!)
                }
                if copyResult == kCMBlockBufferNoErr {
                    value.rmsMeasuredBuffers += 1
                    var sum = 0.0
                    data.withUnsafeBytes { raw in
                        for offset in stride(from: 0, through: length - 4, by: 4) {
                            let sample = Double(raw.loadUnaligned(fromByteOffset: offset, as: Float.self))
                            if sample.isFinite { sum += sample * sample }
                        }
                    }
                    value.peakRMS = max(value.peakRMS, sqrt(sum / Double(max(1, length / 4))))
                }
            }
        }
        metrics[source] = value
    }

    func report() -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        let now = ProcessInfo.processInfo.systemUptime
        return ["kind": "native_capture_metrics", "os": ProcessInfo.processInfo.operatingSystemVersionString,
                "duration_seconds": max(0, now - startedAt),
                "sources": metrics.mapValues { $0.report(now: now) }, "errors": errors,
                "raw_audio_saved": false, "audio_uploaded": false,
                "interpretation": "Buffers and timestamps alone do not establish speech recognition accuracy or perfect capture."]
    }
}

func magentaRatio(_ image: CGImage) -> Double {
    let width = image.width, height = image.height
    var data = [UInt8](repeating: 0, count: width * height * 4)
    return data.withUnsafeMutableBytes { raw in
        guard let context = CGContext(data: raw.baseAddress, width: width, height: height,
            bitsPerComponent: 8, bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        var matched = 0
        for index in stride(from: 0, to: raw.count, by: 4) {
            if raw[index] > 200 && raw[index + 1] < 65 && raw[index + 2] > 180 { matched += 1 }
        }
        return Double(matched) / Double(width * height)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var overlay: NSPanel!
    var status: NSTextField!
    var details: NSTextView!
    var microphone: NSButton!
    var startButton: NSButton!
    var screenshotButton: NSButton!
    var stopButton: NSButton!
    var timer: Timer?
    var deadline: Timer?
    var experimentInProgress = false
    var finishing = false
    let capture = CaptureProbe()
    let results = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("spikes/results/local/native", isDirectory: true)

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 610),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Crackit — Native Feasibility Probe"; window.center()
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 22),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -22),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 22),
            stack.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor, constant: -22)])
        let title = NSTextField(labelWithString: "Measure capture before building the product")
        title.font = .systemFont(ofSize: 22, weight: .semibold); stack.addArrangedSubview(title)
        let explanation = NSTextField(wrappingLabelWithString:
            "Nothing is captured on launch. Start a 15-second audio probe to measure system audio and optional microphone buffers. No audio is saved or uploaded. Use a controlled sample and headphones; stop any unrelated audio first.")
        stack.addArrangedSubview(explanation)
        microphone = NSButton(checkboxWithTitle: "Include microphone (requests microphone permission)", target: nil, action: nil)
        microphone.state = .off; stack.addArrangedSubview(microphone)
        let row = NSStackView(); row.orientation = .horizontal; row.spacing = 10
        startButton = NSButton(title: "Start 15-second audio probe", target: self, action: #selector(start))
        stopButton = NSButton(title: "Stop", target: self, action: #selector(stop)); stopButton.isEnabled = false
        row.addArrangedSubview(startButton); row.addArrangedSubview(stopButton); stack.addArrangedSubview(row)
        screenshotButton = NSButton(title: "Test this overlay with ScreenCaptureKit", target: self, action: #selector(testOverlay))
        stack.addArrangedSubview(screenshotButton)
        stack.addArrangedSubview(NSTextField(wrappingLabelWithString:
            "The overlay test captures only the probe’s own magenta window twice. It checks one local capture path, not Zoom/Teams/Meet or remote sharing. It saves metrics only. Sharing protection starts OFF."))
        status = NSTextField(wrappingLabelWithString: "Idle. No capture running."); stack.addArrangedSubview(status)
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder
        details = NSTextView(); details.isEditable = false; details.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        scroll.documentView = details; stack.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 170).isActive = true
        overlay = NSPanel(contentRect: NSRect(x: 100, y: 120, width: 360, height: 120),
                          styleMask: [.titled, .nonactivatingPanel], backing: .buffered, defer: false)
        overlay.title = "CRACKIT_CONTROLLED_OVERLAY"; overlay.level = .floating
        overlay.backgroundColor = NSColor(srgbRed: 1, green: 0, blue: 1, alpha: 1)
        overlay.sharingType = .readOnly
        let sentinel = NSTextField(labelWithString: "CRACKIT — CAPTURE TEST\nProtection OFF")
        sentinel.frame = NSRect(x: 18, y: 30, width: 320, height: 60)
        sentinel.font = .systemFont(ofSize: 20, weight: .bold); sentinel.textColor = .black
        overlay.contentView?.addSubview(sentinel)
        capture.onUnexpectedStop = { [weak self] in Task { @MainActor in await self?.finishCapture() } }
        window.makeKeyAndOrderFront(nil); overlay.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    func show(_ data: [String: Any]) {
        if let encoded = try? JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: encoded, encoding: .utf8) { details.string = text }
    }

    func save(_ data: [String: Any], prefix: String) {
        do {
            try FileManager.default.createDirectory(at: results, withIntermediateDirectories: true)
            let path = results.appendingPathComponent(prefix + "-" + UUID().uuidString + ".json")
            let encoded = try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys])
            try encoded.write(to: path, options: .atomic)
            status.stringValue += "\nReport: " + path.path
        } catch { status.stringValue += "\nCould not save metrics: " + error.localizedDescription }
    }

    func setBusy(_ busy: Bool) {
        experimentInProgress = busy; startButton.isEnabled = !busy
        screenshotButton.isEnabled = !busy; microphone.isEnabled = !busy
    }

    @objc func start() {
        guard !experimentInProgress else { return }
        setBusy(true); status.stringValue = "Starting. macOS may request recording permissions."
        Task {
            do {
                if microphone.state == .on {
                    let allowed = await AVCaptureDevice.requestAccess(for: .audio)
                    if !allowed { throw NSError(domain: "Crackit", code: 5, userInfo: [NSLocalizedDescriptionKey: "Microphone permission denied; capture did not start"]) }
                }
                try await capture.start(microphone: microphone.state == .on)
                stopButton.isEnabled = true; status.stringValue = "Capturing metrics for 15 seconds. Raw audio is not saved."
                timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                    Task { @MainActor in guard let self = self else { return }; self.show(self.capture.report()) }
                }
                deadline = Timer.scheduledTimer(withTimeInterval: 15, repeats: false) { [weak self] _ in
                    Task { @MainActor in await self?.finishCapture() }
                }
            } catch {
                await capture.stop(); status.stringValue = "Capture failed: " + error.localizedDescription
                setBusy(false); stopButton.isEnabled = false
            }
        }
    }

    @objc func stop() { Task { await finishCapture() } }

    func finishCapture() async {
        guard experimentInProgress && !finishing else { return }
        finishing = true; stopButton.isEnabled = false
        timer?.invalidate(); deadline?.invalidate(); timer = nil; deadline = nil
        await capture.stop(); let report = capture.report(); show(report)
        status.stringValue = "Capture stopped."; save(report, prefix: "audio")
        setBusy(false); finishing = false
    }

    func captureOverlay() async throws -> [String: Any] {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let own = content.windows.first(where: { $0.windowID == CGWindowID(overlay.windowNumber) }) else {
            return ["status": "window_not_listed", "magenta_ratio": 0]
        }
        let configuration = SCStreamConfiguration()
        configuration.width = 720; configuration.height = 280
        configuration.showsCursor = false
        let image = try await SCScreenshotManager.captureImage(contentFilter: SCContentFilter(desktopIndependentWindow: own), configuration: configuration)
        return ["status": "captured", "width": image.width, "height": image.height,
                "magenta_ratio": magentaRatio(image)]
    }

    @objc func testOverlay() {
        guard !experimentInProgress else { return }
        setBusy(true); status.stringValue = "Testing only this app’s overlay."
        Task {
            defer { overlay.sharingType = .readOnly; setBusy(false) }
            do {
                overlay.sharingType = .readOnly
                try await Task.sleep(nanoseconds: 500_000_000)
                let baseline = try await captureOverlay()
                overlay.sharingType = .none
                try await Task.sleep(nanoseconds: 500_000_000)
                let restricted = try await captureOverlay()
                let baselineRatio = baseline["magenta_ratio"] as? Double ?? 0
                let restrictedRatio = restricted["magenta_ratio"] as? Double ?? 0
                let result = baselineRatio < 0.05 ? "inconclusive_baseline" :
                    restricted["status"] as? String == "window_not_listed" ? "inconclusive_window_not_listed" :
                    restrictedRatio > 0.05 ? "overlay_visible_despite_sharing_none" : "marker_not_observed_in_this_path"
                let report: [String: Any] = ["kind": "local_overlay_capture_test", "os": ProcessInfo.processInfo.operatingSystemVersionString,
                    "path": "ScreenCaptureKit desktopIndependentWindow / SCScreenshotManager",
                    "baseline": baseline, "sharing_none": restricted, "result": result,
                    "raw_screenshots_saved": false,
                    "remote_conferencing_tested": false,
                    "interpretation": "A local selected-window test does not establish full-display or conferencing-app exclusion."]
                show(report); status.stringValue = result; save(report, prefix: "overlay")
            } catch { status.stringValue = "Overlay test failed: " + error.localizedDescription }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { timer?.invalidate(); deadline?.invalidate() }
}

@main
struct ProbeMain {
@MainActor static func main() {
let arguments = CommandLine.arguments
if arguments.contains("--capabilities") {
    emit(["kind": "native_capabilities", "os": ProcessInfo.processInfo.operatingSystemVersionString,
          "architecture": "arm64", "minimum_os": "macOS 15", "screen_capture_preflight": CGPreflightScreenCaptureAccess(),
          "microphone_authorization_raw": AVCaptureDevice.authorizationStatus(for: .audio).rawValue,
          "capture_started": false, "permissions_requested": false,
          "compiled_features": ["ScreenCaptureKit system audio", "ScreenCaptureKit microphone", "AppKit overlay", "own-window screenshot test", "16kHz mono PCM conversion", "local live PCM frame bridge"]])
} else if arguments.count == 4 && arguments[1] == "--convert-audio" {
    do { try convertAudio(arguments[2], arguments[3]) }
    catch { emit(["error": error.localizedDescription]); exit(1) }
} else if arguments.count >= 3 && arguments[1] == "--live-frames" {
    let microphoneRequested = arguments.contains("--mic")
    let socketIndex = arguments.firstIndex(of: "--socket")
    let socketPath = socketIndex.flatMap { $0 + 1 < arguments.count ? arguments[$0 + 1] : nil }
    let expectedCount = 3 + (microphoneRequested ? 1 : 0) + (socketPath == nil ? 0 : 2)
    guard let seconds = Double(arguments[2]), seconds > 0, seconds <= 3600,
          arguments.count == expectedCount,
          socketIndex == nil || socketPath != nil else {
        fputs("Usage: CrackitProbe --live-frames SECONDS [--mic] [--socket PATH] (1..3600)\n", stderr)
        exit(2)
    }
    let capture = LiveFrames()
    Task { @MainActor in
        do {
            if let socketPath = socketPath { try configureLiveSocket(socketPath) }
            try await capture.start(microphone: microphoneRequested)
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            await capture.stop()
            exit(0)
        } catch {
            liveLine(["kind": "capture_error", "message": error.localizedDescription])
            await capture.stop()
            exit(1)
        }
    }
    RunLoop.main.run()
} else {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate; app.setActivationPolicy(.regular); app.run()
}
}
}
