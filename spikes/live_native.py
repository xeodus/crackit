"""Explicit, short macOS capture -> PCM -> v2 source router diagnostic.

Only JSON metrics and finalized text are saved. Native PCM frames are decoded
in memory and are never written to a file or sent to a hosted provider.
"""
import argparse
import base64
import binascii
import hashlib
import json
import os
import socket
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone

from .core import ContextStore
from .lab import ROOT, write_json
from .metrics import percentile, word_error_rate
from .streaming import apply_event
from .transport import local_router


class PCMChunker:
    """Preserve the native sample clock and explicitly reset on a real gap."""
    def __init__(self, source, router, tolerance_ms=20):
        if source not in ('system', 'mic'):
            raise ValueError('Unknown audio source')
        self.source = source
        self.router = router
        self.tolerance_ms = tolerance_ms
        self.base_ms = None
        self.received_samples = 0
        self.sent_samples = 0
        self.pending = bytearray()
        self.discontinuities = 0
        self.frames = 0
        self.samples = 0

    def feed(self, start_ms, pcm):
        if not isinstance(start_ms, int) or start_ms < 0 or not pcm or len(pcm) % 2:
            raise ValueError('Invalid 16kHz PCM frame')
        if self.base_ms is None:
            self.base_ms = start_ms
        else:
            expected = self.base_ms + self.received_samples * 1000 // 16000
            if abs(start_ms - expected) > self.tolerance_ms:
                self.discontinuities += 1
                self.pending.clear()
                self.router.reset(self.source, start_ms, 'native_timestamp_discontinuity')
                self.base_ms = start_ms
                self.received_samples = 0
                self.sent_samples = 0
        self.pending.extend(pcm)
        count = len(pcm) // 2
        self.received_samples += count
        self.samples += count
        self.frames += 1
        while len(self.pending) >= 1024:
            block = bytes(self.pending[:1024])
            del self.pending[:1024]
            self.router.feed(self.source, self.base_ms + self.sent_samples * 1000 // 16000, block)
            self.sent_samples += 512

    def finish(self):
        if self.pending:
            self.router.feed(self.source, self.base_ms + self.sent_samples * 1000 // 16000,
                             bytes(self.pending))
            self.pending.clear()

    def report(self):
        return {'native_frames': self.frames, 'pcm_samples': self.samples,
                'timestamp_discontinuities': self.discontinuities}


def run_live(seconds=15, microphone=False, model='base.en', expected=None, out=None,
             play_wav=None, expect_phrase=None):
    if not 1 <= seconds <= 3600:
        raise ValueError('Capture duration must be 1..3600 seconds')
    destination = Path(out or ROOT / 'spikes/results/local/native/live-transcript.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    executable = ROOT / '.build/CrackitProbe.app/Contents/MacOS/CrackitProbe'
    if not executable.exists() or not (ROOT / '.build/whisper-stream-v2').exists():
        raise FileNotFoundError('Run make native and make local-engine first')
    if play_wav is not None:
        play_wav = Path(play_wav)
        if not play_wav.is_file():
            raise FileNotFoundError(play_wav)
        digest = hashlib.sha256()
        with play_wav.open('rb') as audio_file:
            for block in iter(lambda: audio_file.read(1024 * 1024), b''):
                digest.update(block)
        playback_sha256 = digest.hexdigest()
    else:
        playback_sha256 = None
    socket_folder = tempfile.TemporaryDirectory(dir='/private/tmp', prefix='crackit-live-')
    socket_path = str(Path(socket_folder.name) / 'frames.sock')
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)
    server.settimeout(30)
    command = ['open', '-n', '-a', str(executable.parent.parent.parent), '--args',
               '--live-frames', str(seconds), '--socket', socket_path]
    if microphone:
        command.append('--mic')
    stderr_path = destination.with_suffix('.native.stderr.txt')
    log = stderr_path.open('w')
    process = None
    player = None
    event_queue = queue.Queue(maxsize=4096)
    callback_errors = []
    frame_timing = {source: {'frames': 0, 'max_receive_interval_ms': 0.0,
                             'max_decode_and_route_ms': 0.0,
                             'max_capture_to_receive_drift_ms': 0.0,
                             'last_received': None, 'first_clock_offset_ms': None}
                    for source in ('system', 'mic')}
    timing_incidents = []
    resource_samples = []
    resource_sample_failures = 0
    resource_stop = threading.Event()
    native_pid = None

    def sample_resources():
        nonlocal resource_sample_failures
        while not resource_stop.is_set():
            pids = [os.getpid()]
            if native_pid is not None:
                pids.append(native_pid)
            with router.lock:
                pids.extend(state['decoder'].process.pid for state in router.sources.values()
                            if state['decoder'] is not None)
            try:
                output = subprocess.check_output(
                    ['ps', '-o', 'pid=,%cpu=,rss=', '-p', ','.join(map(str, sorted(set(pids))))],
                    text=True, stderr=subprocess.DEVNULL, timeout=2)
                processes = []
                for line in output.splitlines():
                    pid, cpu, rss = line.split()
                    processes.append({'pid': int(pid), 'cpu_percent': float(cpu),
                                      'rss_kib': int(rss)})
                resource_samples.append({'at_monotonic': time.monotonic(),
                                         'processes': processes})
            except (OSError, ValueError, subprocess.SubprocessError):
                resource_sample_failures += 1
            resource_stop.wait(5)

    def on_event(event):
        try:
            event_queue.put_nowait((event, time.monotonic()))
        except queue.Full:
            callback_errors.append('Transcript event queue overflow')

    run_log_folder = destination.parent / 'worker-logs' / (destination.stem + '-' +
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    router = local_router(run_log_folder, on_event, model=model,
                          worker_version='v2')
    resource_thread = threading.Thread(target=sample_resources, daemon=True)
    chunkers = {source: PCMChunker(source, router) for source in ('system', 'mic')}
    native_report = None
    errors = []
    started = False
    capture_started_wall = None
    begin = time.monotonic()
    connection = None
    reader = None
    prewarm_ms = None
    router_finished = False
    try:
        warm_start = time.monotonic()
        router.prepare('system')
        if microphone:
            router.prepare('mic')
        prewarm_ms = (time.monotonic() - warm_start) * 1000
        resource_thread.start()
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        if process.wait(timeout=10) != 0:
            raise RuntimeError('LaunchServices could not start the probe')
        connection, _ = server.accept()
        connection.settimeout(seconds + 60)
        reader = connection.makefile('r', encoding='utf-8')
        for line in reader:
            try:
                item = json.loads(line)
                kind = item.get('kind')
                if kind == 'started':
                    started = True
                    native_pid = item.get('pid') if isinstance(item.get('pid'), int) else None
                    capture_started_wall = time.monotonic()
                    if play_wav is not None:
                        player = subprocess.Popen(['afplay', str(play_wav)],
                                                  stdout=subprocess.DEVNULL, stderr=log)
                elif kind == 'frame':
                    source = item['source']
                    if source not in chunkers or item['sample_rate'] != 16000:
                        raise ValueError('Invalid native source or sample rate')
                    received_at = time.monotonic()
                    timing = frame_timing[source]
                    if timing['last_received'] is not None:
                        timing['max_receive_interval_ms'] = max(
                            timing['max_receive_interval_ms'],
                            (received_at - timing['last_received']) * 1000)
                    timing['last_received'] = received_at
                    timing['frames'] += 1
                    clock_offset = received_at * 1000 - item['start_ms']
                    if timing['first_clock_offset_ms'] is None:
                        timing['first_clock_offset_ms'] = clock_offset
                    drift = clock_offset - timing['first_clock_offset_ms']
                    timing['max_capture_to_receive_drift_ms'] = max(
                        timing['max_capture_to_receive_drift_ms'], abs(drift))
                    pcm = base64.b64decode(item['pcm_b64'], validate=True)
                    if len(pcm) != item['samples'] * 2:
                        raise ValueError('Native PCM byte count mismatch')
                    chunkers[source].feed(item['start_ms'], pcm)
                    timing['max_decode_and_route_ms'] = max(
                        timing['max_decode_and_route_ms'],
                        (time.monotonic() - received_at) * 1000)
                    route_ms = (time.monotonic() - received_at) * 1000
                    if (route_ms > 100 or drift > 1000) and len(timing_incidents) < 200:
                        timing_incidents.append({'source':source,'audio_start_ms':item['start_ms'],
                                                 'route_ms':route_ms,'receive_drift_ms':drift})
                elif kind == 'capture_report':
                    native_report = item
                elif kind == 'capture_error':
                    errors.append(item.get('message', 'Native capture error'))
                else:
                    raise ValueError('Unknown native output kind')
            except (KeyError, ValueError, TypeError, binascii.Error) as error:
                errors.append(type(error).__name__ + ': ' + str(error))
                break
        for chunker in chunkers.values():
            chunker.finish()
        router.finish()
        router_finished = True
    except Exception as error:
        errors.append(type(error).__name__ + ': ' + str(error))
    finally:
        resource_stop.set()
        if resource_thread.is_alive():
            resource_thread.join(timeout=3)
        if not router_finished:
            router.abort()
        if reader is not None:
            reader.close()
        if connection is not None:
            connection.close()
        server.close()
        socket_folder.cleanup()
        if process is not None and process.poll() is None:
            process.terminate(); process.wait()
        if player is not None and player.poll() is None:
            player.terminate()
            try: player.wait(timeout=2)
            except subprocess.TimeoutExpired: player.kill(); player.wait()
        log.close()
    received_events = []
    while not event_queue.empty():
        received_events.append(event_queue.get_nowait())
    events = [event for event, _ in received_events]
    store = ContextStore()
    store.start('live', 'interview')
    try:
        for event in events:
            try:
                apply_event(store, 'live', 'interview', event)
            except Exception as error:
                errors.append('Context event error: ' + str(error))
        final_segments = [row for row in store.transcript('live', 'interview')
                          if row['state'] == 'final' and row['text'].strip()]
        transcript = ' '.join(row['text'].strip() for row in final_segments)
        transcripts_by_source = {source: ' '.join(row['text'].strip() for row in final_segments
                                                  if row['source'] == source)
                                 for source in ('system', 'mic')}
    finally:
        store.close()
    errors.extend(callback_errors)
    if not started:
        errors.append('Native capture did not start')
    if process is None or process.returncode != 0:
        errors.append('LaunchServices exited with code ' + str(process.returncode if process else 'not_started'))
    if native_report is None:
        errors.append('Native capture report missing')
    elif native_report.get('errors'):
        errors.extend(native_report['errors'])
    selected = ['system'] + (['mic'] if microphone else [])
    for source in selected:
        stats = (native_report or {}).get('sources', {}).get(source, {})
        if stats.get('emitted_samples', 0) == 0:
            errors.append(source + ' emitted no converted PCM')
        if stats.get('converter_errors', 0) or stats.get('invalid_buffers', 0):
            errors.append(source + ' had conversion or buffer errors')
    if player is not None and player.returncode != 0:
        errors.append('Controlled playback did not finish successfully')
    decoder_metrics = {}
    for source, state in router.sources.items():
        decoder = state['decoder']
        decoder_metrics[source] = {'epoch': state['epoch'],
                                   'pid': decoder.process.pid,
                                   'max_queue_chunks': decoder.max_queue_chunks,
                                   'timing': {k:v for k,v in decoder.timing.items() if k!='last_read'},
                                   'timing_incidents': decoder.timing_incidents,
                                   'worker_summary': decoder.summary}
    final_delays = [
        (arrived - capture_started_wall) * 1000 - event.end_ms
        for event, arrived in received_events
        if capture_started_wall is not None and event.state == 'final' and event.text.strip()
    ]
    result = {'kind': 'native_live_transcription_probe', 'worker_version': 'v2',
              'capture_seconds_requested': seconds, 'wall_seconds': time.monotonic() - begin,
              'run_start_monotonic': begin,
              'prewarm_ms': prewarm_ms,
              'native_pid': native_pid,
              'worker_log_directory': str(run_log_folder),
              'frame_timing': {source: {key: value for key, value in timing.items()
                                        if key not in ('last_received','first_clock_offset_ms')}
                               for source, timing in frame_timing.items()},
              'timing_incidents': timing_incidents,
              'resource_samples': resource_samples,
              'resource_sample_failures': resource_sample_failures,
              'retired_decoder_epochs': router.retired_epochs,
              'native': native_report, 'transport': {k: v.report() for k, v in chunkers.items()},
              'decoders': decoder_metrics,
              'transcript': transcript, 'transcript_by_source': transcripts_by_source,
              'final_segments': len(final_segments),
              'word_end_delay_proxy_ms': {
                  'count': len(final_delays),
                  'p50': percentile(final_delays, 50) if final_delays else None,
                  'p95': percentile(final_delays, 95) if final_delays else None,
                  'note': 'Recognizer word-end proxy; not independently annotated speech-end latency.'},
              'gaps': [event.__dict__ for event in events if event.state == 'gap'],
              'errors': errors, 'status': 'pending_assessment',
              'raw_audio_saved': False, 'audio_uploaded': False,
              'controlled_playback': str(play_wav) if play_wav is not None else None,
              'controlled_playback_sha256': playback_sha256,
              'interpretation': 'A controlled audible signal and reference text are required to establish recognition; levels alone are insufficient.'}
    if expected is not None:
        result['reference_comparison'] = word_error_rate(expected, transcripts_by_source['system'])
    if play_wav is not None and (expected is not None or expect_phrase is not None):
        system_rms = (native_report or {}).get('sources', {}).get('system', {}).get('peak_rms', 0)
        phrase_match = expect_phrase is not None and expect_phrase.casefold() in transcripts_by_source['system'].casefold()
        reference_match = expected is not None and result['reference_comparison']['wer'] is not None \
            and result['reference_comparison']['wer'] <= 0.30
        result['controlled_signal_verified'] = bool(player is not None and player.returncode == 0
            and system_rms >= 0.005 and (phrase_match or reference_match))
        result['expected_phrase_found'] = phrase_match if expect_phrase is not None else None
    had_gap = bool(result['gaps']) or any(
        (native_report or {}).get('sources', {}).get(source, {}).get('timestamp_gaps_over_100ms', 0)
        for source in selected)
    failed_signal = 'controlled_signal_verified' in result and not result['controlled_signal_verified']
    result['status'] = 'completed' if not errors and not had_gap and not failed_signal else 'incomplete'
    write_json(destination, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--mic', action='store_true')
    parser.add_argument('--model', choices=['base.en', 'small.en'], default='base.en')
    parser.add_argument('--expected', help='Known controlled spoken text; optional WER reference')
    parser.add_argument('--expected-file', type=Path, help='UTF-8 reference transcript file')
    parser.add_argument('--play-wav', type=Path, help='Play a controlled WAV after capture starts')
    parser.add_argument('--expect-phrase', help='Phrase expected in a known controlled playback')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--summary-only', action='store_true',
                        help='Print metrics without the full transcript')
    args = parser.parse_args()
    if args.expected is not None and args.expected_file is not None:
        parser.error('Use only one of --expected or --expected-file')
    expected = args.expected_file.read_text().strip() if args.expected_file else args.expected
    result = run_live(args.seconds, args.mic, args.model, expected, args.out,
                      args.play_wav, args.expect_phrase)
    printed = {k: v for k, v in result.items()
               if k not in ('transcript', 'transcript_by_source')} if args.summary_only else result
    print(json.dumps(printed, indent=2))
    raise SystemExit(0 if result['status'] == 'completed' else 1)
