import AppKit
import AVFoundation
import CoreMedia
import ScreenCaptureKit
import Darwin

private let liveOutputLock = NSLock()
private var liveOutputHandle = FileHandle.standardOutput

func configureLiveSocket(_ path: String) throws {
    let bytes = Array(path.utf8CString)
    var address = sockaddr_un()
    let capacity = MemoryLayout.size(ofValue: address.sun_path)
    guard !bytes.isEmpty, bytes.count <= capacity else {
        throw NSError(domain: "Crackit", code: 33,
                      userInfo: [NSLocalizedDescriptionKey: "Local socket path is too long"])
    }
    address.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutableBytes(of: &address.sun_path) { raw in
        for (index, byte) in bytes.enumerated() { raw[index] = UInt8(bitPattern: byte) }
    }
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
    let connected = withUnsafePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            Darwin.connect(descriptor, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard connected == 0 else {
        let code = errno
        Darwin.close(descriptor)
        throw NSError(domain: NSPOSIXErrorDomain, code: Int(code))
    }
    liveOutputLock.withLock {
        liveOutputHandle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    }
}

func liveLine(_ object: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else { return }
    liveOutputLock.withLock {
        liveOutputHandle.write(data)
        liveOutputHandle.write(Data([10]))
    }
}

private struct LiveSourceStats {
    var buffers = 0
    var emittedSamples = 0
    var peakRMS = 0.0
    var nonSilentBuffers = 0
    var invalidBuffers = 0
    var converterErrors = 0
    var timestampGaps = 0
    var previousEnd: Double?
    var previousCallbackUptime: Double?
    var maxCallbackIntervalMs = 0.0
    var maxSocketWriteMs = 0.0
    var slowSocketWrites = 0

    func report() -> [String: Any] {
        ["buffers": buffers, "emitted_samples": emittedSamples,
         "peak_rms": peakRMS, "non_silent_buffers": nonSilentBuffers,
         "invalid_buffers": invalidBuffers, "converter_errors": converterErrors,
         "timestamp_gaps_over_100ms": timestampGaps,
         "max_callback_interval_ms": maxCallbackIntervalMs,
         "max_socket_write_ms": maxSocketWriteMs,
         "socket_writes_over_100ms": slowSocketWrites]
    }
}

/// A short, explicitly started diagnostic. Frame payloads travel only over stdout
/// to the local router; no PCM files or screenshots are created.
final class LiveFrames: NSObject, SCStreamOutput, SCStreamDelegate {
    private let lock = NSLock()
    private var stream: SCStream?
    private var converters: [String: AVAudioConverter] = [:]
    private var formatKeys: [String: String] = [:]
    private var stats: [String: LiveSourceStats] = [:]
    private var errors: [String] = []
    private var startedAt = 0.0
    private var stopped = false

    func start(microphone: Bool) async throws {
        if microphone {
            let allowed = await AVCaptureDevice.requestAccess(for: .audio)
            if !allowed {
                throw NSError(domain: "Crackit", code: 31,
                              userInfo: [NSLocalizedDescriptionKey: "Microphone permission denied"])
            }
        }
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else {
            throw NSError(domain: "Crackit", code: 32,
                          userInfo: [NSLocalizedDescriptionKey: "No display available for audio capture"])
        }
        let config = SCStreamConfiguration()
        config.width = 2; config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.queueDepth = 3
        config.capturesAudio = true
        config.captureMicrophone = microphone
        config.excludesCurrentProcessAudio = false
        config.sampleRate = 48000
        config.channelCount = 1
        config.showsCursor = false
        let candidate = SCStream(filter: SCContentFilter(display: display, excludingWindows: []),
                                 configuration: config, delegate: self)
        try candidate.addStreamOutput(self, type: .audio,
                                      sampleHandlerQueue: DispatchQueue(label: "dev.crackit.live.system"))
        if microphone {
            try candidate.addStreamOutput(self, type: .microphone,
                                          sampleHandlerQueue: DispatchQueue(label: "dev.crackit.live.mic"))
        }
        lock.withLock {
            stats = ["system": LiveSourceStats()]
            if microphone { stats["mic"] = LiveSourceStats() }
            converters = [:]; formatKeys = [:]; errors = []
            startedAt = ProcessInfo.processInfo.systemUptime
            stopped = false
        }
        stream = candidate
        try await candidate.startCapture()
        liveLine(["kind": "started", "microphone": microphone,
                  "pid": ProcessInfo.processInfo.processIdentifier,
                  "os": ProcessInfo.processInfo.operatingSystemVersionString])
    }

    func stop() async {
        if let stream = stream {
            do { try await stream.stopCapture() }
            catch { lock.withLock { errors.append("stop: " + error.localizedDescription) } }
        }
        stream = nil
        let report: [String: Any] = lock.withLock {
            stopped = true
            return ["kind": "capture_report", "duration_seconds":
                    startedAt > 0 ? max(0, ProcessInfo.processInfo.systemUptime - startedAt) : 0,
                    "sources": stats.mapValues { $0.report() }, "errors": errors,
                    "raw_audio_saved": false, "audio_uploaded": false]
        }
        liveLine(report)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        lock.withLock { errors.append("stream: " + error.localizedDescription) }
        liveLine(["kind": "capture_error", "message": error.localizedDescription])
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer buffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio || type == .microphone else { return }
        let source = type == .microphone ? "mic" : "system"
        guard buffer.isValid, CMSampleBufferDataIsReady(buffer),
              let description = buffer.formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(description),
              let inputFormat = AVAudioFormat(streamDescription: asbd),
              let target = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000,
                                         channels: 1, interleaved: true),
              buffer.presentationTimeStamp.seconds.isFinite else {
            lock.withLock { stats[source, default: LiveSourceStats()].invalidBuffers += 1 }
            return
        }
        let pts = buffer.presentationTimeStamp.seconds
        let sampleCount = CMSampleBufferGetNumSamples(buffer)
        guard sampleCount > 0 else { return }
        let key = "\(asbd.pointee.mSampleRate)/\(asbd.pointee.mChannelsPerFrame)/\(asbd.pointee.mFormatFlags)/\(asbd.pointee.mBitsPerChannel)"
        let converter: AVAudioConverter? = lock.withLock {
            var value = stats[source, default: LiveSourceStats()]
            value.buffers += 1
            let callbackUptime = ProcessInfo.processInfo.systemUptime
            if let prior = value.previousCallbackUptime {
                value.maxCallbackIntervalMs = max(value.maxCallbackIntervalMs,
                                                  (callbackUptime - prior) * 1000)
            }
            value.previousCallbackUptime = callbackUptime
            if let prior = value.previousEnd, abs(pts - prior) > 0.1 {
                value.timestampGaps += 1
            }
            value.previousEnd = pts + Double(sampleCount) / inputFormat.sampleRate
            stats[source] = value
            if formatKeys[source] != key {
                formatKeys[source] = key
                converters[source] = AVAudioConverter(from: inputFormat, to: target)
            }
            return converters[source]
        }
        guard let converter = converter else {
            lock.withLock { stats[source, default: LiveSourceStats()].converterErrors += 1 }
            return
        }
        let capacity = AVAudioFrameCount(ceil(Double(sampleCount) * 16000 / inputFormat.sampleRate) + 128)
        guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
        var converted = false
        var conversionError: NSError?
        let status = try? buffer.withAudioBufferList { list, _ -> AVAudioConverterOutputStatus in
            guard let input = AVAudioPCMBuffer(pcmFormat: inputFormat,
                                                bufferListNoCopy: list.unsafePointer) else { return .error }
            return converter.convert(to: output, error: &conversionError) { _, state in
                if converted { state.pointee = .noDataNow; return nil }
                converted = true
                state.pointee = .haveData
                return input
            }
        }
        guard status != nil, status != .error, conversionError == nil,
              output.frameLength > 0, let samples = output.int16ChannelData?.pointee else {
            lock.withLock { stats[source, default: LiveSourceStats()].converterErrors += 1 }
            return
        }
        let count = Int(output.frameLength)
        var sum = 0.0
        for index in 0..<count {
            let sample = Double(samples[index]) / 32768.0
            sum += sample * sample
        }
        let rms = sqrt(sum / Double(count))
        let elapsed = max(0, pts - lock.withLock { startedAt })
        let payload = Data(bytes: samples, count: count * 2).base64EncodedString()
        let shouldEmit = lock.withLock { () -> Bool in
            guard !stopped else { return false }
            var value = stats[source, default: LiveSourceStats()]
            value.emittedSamples += count
            value.peakRMS = max(value.peakRMS, rms)
            if rms >= 0.005 { value.nonSilentBuffers += 1 }
            stats[source] = value
            return true
        }
        guard shouldEmit else { return }
        let writeStart = ProcessInfo.processInfo.systemUptime
        liveLine(["kind": "frame", "source": source,
                  "start_ms": Int((elapsed * 1000).rounded()),
                  "sample_rate": 16000, "samples": count,
                  "pcm_b64": payload])
        let writeMs = (ProcessInfo.processInfo.systemUptime - writeStart) * 1000
        lock.withLock {
            var value = stats[source, default: LiveSourceStats()]
            value.maxSocketWriteMs = max(value.maxSocketWriteMs, writeMs)
            if writeMs > 100 { value.slowSocketWrites += 1 }
            stats[source] = value
        }
    }
}
