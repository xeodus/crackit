"""Controlled on-device Whisper benchmarks, with explicit offline/streaming limits."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
import wave

from .lab import ROOT, write_json
from .metrics import percentile, word_error_rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--backend', choices=['cpu', 'metal'], default='cpu')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--causal-replay', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.runs <= 10: raise ValueError('Runs must be 1..10')
    model = ROOT/'.cache/whisper.cpp/models/ggml-base.en.bin'
    cli = ROOT/'.cache/whisper.cpp/build/bin/whisper-cli'
    with wave.open(str(args.wav), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getcomptype()) != (16000, 1, 2, 'NONE'):
            raise ValueError('Expected 16kHz mono signed PCM WAV')
        duration = audio.getnframes()/16000; pcm = audio.readframes(audio.getnframes())
    if not 0 < duration <= 30: raise ValueError('Controlled experiment is limited to 30 seconds')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    timings = []; outputs = []
    for index in range(args.runs):
        prefix = args.out.parent / ('%s-run-%d' % (args.backend, index))
        command = [str(cli), '-m', str(model), '-f', str(args.wav), '-t', '4',
                   '-l', 'en', '-bs', '1', '-bo', '1', '-nf', '-oj', '-of', str(prefix)]
        if args.backend == 'cpu': command.append('-ng')
        start = time.perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, timeout=90)
        elapsed = time.perf_counter()-start
        (Path(str(prefix)+'.stderr.txt')).write_text(process.stderr)
        if process.returncode:
            raise RuntimeError('Local recognizer failed; inspect ' + str(prefix) + '.stderr.txt')
        output = json.loads(Path(str(prefix)+'.json').read_text())
        hypothesis = ' '.join(s['text'].strip() for s in output.get('transcription', []))
        timings.append(elapsed)
        outputs.append({'run': index, 'wall_seconds': elapsed, 'real_time_factor': elapsed/duration,
                        'transcript': hypothesis, 'word_error': word_error_rate(args.reference.read_text(), hypothesis)})
    commit = subprocess.check_output(['git', '-C', str(ROOT/'.cache/whisper.cpp'), 'rev-parse', 'HEAD'], text=True).strip()
    result = {'kind': 'controlled_local_stt', 'generated_at': datetime.now(timezone.utc).isoformat(),
              'environment': platform.platform(), 'backend_requested': args.backend,
              'implementation': 'whisper.cpp', 'commit': commit, 'model': 'base.en',
              'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
              'audio_sha256': hashlib.sha256(args.wav.read_bytes()).hexdigest(),
              'audio_seconds': duration, 'runs': outputs,
              'wall_seconds': {'p50': percentile(timings, 50), 'p95': percentile(timings, 95)},
              'limitations': ['Synthetic TTS only; not representative conversational accuracy',
                              'Whole-file inference includes process/model startup; not streaming latency',
                              'Requested Metal must be checked against the backend log for actual GPU use',
                              'Three runs do not establish stable tail percentiles or thermal behavior']}
    if args.causal_replay:
        raw = args.out.parent/'controlled.pcm'; raw.write_bytes(pcm)
        command = [str(ROOT/'.build/whisper-replay'), str(model), str(raw), args.backend]
        replay = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (args.out.parent/('causal-'+args.backend+'.stderr.txt')).write_text(replay.stderr)
        if replay.returncode: raise RuntimeError('Causal replay failed; inspect backend log')
        events = [json.loads(line) for line in replay.stdout.splitlines() if line.startswith('{')]
        result['causal_replay'] = {'events': events, 'step_seconds': 2, 'persistent_context': True,
            'source_sha256': hashlib.sha256((ROOT/'spikes/native/local_stream.cpp').read_bytes()).hexdigest(),
            'decoder': {'timestamps': True, 'temperature_increment': 0, 'greedy_best_of': 1},
            'paced_in_real_time': False,
            'interpretation': 'Each prefix contains only available audio, but execution is accelerated. '
                              'Agreement is provisional; later revisions are counted. Bounded to one 30-second clip; '
                              'no rolling-buffer or sustained-meeting streaming claim.'}
    write_json(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
