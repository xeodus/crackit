"""Build a local, reproducible 30-minute synthetic interview capture fixture.

Uses macOS say and the probe's AVAudioConverter path. The generated WAV and
manifest stay under ignored results/local and are never uploaded.
"""
import argparse
import json
from pathlib import Path
import random
import subprocess
import tempfile
import wave

from .lab import ROOT, write_json


TURNS = (
    ('Samantha', 'Explain the difference between a process and a thread. How do they share memory?'),
    ('Aman', 'A process has its own address space. Threads in one process share memory, so they need synchronization.'),
    ('Daniel', 'What is a race condition? Show how you would prevent one without holding a lock too long.'),
    ('Aman', 'A race condition depends on the order of concurrent operations. I would protect the shared state with a short critical section.'),
    ('Samantha', 'Given an unsorted array, find two numbers that sum to a target. State the time and space complexity.'),
    ('Aman', 'I would keep a hash map of values already seen. For each value I check whether the complement exists. This takes linear expected time and linear space.'),
    ('Daniel', 'Now suppose the array is too large for memory. Which assumptions would you revisit?'),
    ('Aman', 'I would clarify whether the array is sorted, whether approximate answers are allowed, and whether external storage is available.'),
    ('Samantha', 'Tell me about a time you disagreed with a teammate. What did you personally do, and what was the result?'),
    ('Aman', 'I would use a real example from my experience, explain my specific contribution, and distinguish the outcome from my assumptions.'),
    ('Daniel', 'A patient has a positive screening test. Why is the probability of disease not necessarily the test sensitivity?'),
    ('Aman', 'The posterior probability also depends on prevalence and the false positive rate. I would apply Bayes theorem with the actual base rate.'),
    ('Samantha', 'Why does a model perform well on training data but fail after deployment?'),
    ('Aman', 'Possible causes include data leakage, distribution shift, and a metric that does not match the real decision. I would inspect each separately.'),
    ('Daniel', 'You have two minutes left. Summarize the tradeoff between latency, correctness, and memory for your solution.'),
    ('Aman', 'I would first state the correctness invariant, then give the measured complexity and any assumptions the implementation needs.'),
)


def make_fixture(out, seconds=1800, seed=917):
    if not 60 <= seconds <= 3600:
        raise ValueError('Fixture duration must be 60..3600 seconds')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    converter = ROOT / '.build/CrackitProbe.app/Contents/MacOS/CrackitProbe'
    if not converter.exists():
        raise FileNotFoundError('Run make native first')
    clips = []
    with tempfile.TemporaryDirectory(dir=out.parent, prefix='interview-render-') as temp:
        temp = Path(temp)
        for index, (voice, text) in enumerate(TURNS):
            aiff, wav = temp / f'{index:02d}.aiff', temp / f'{index:02d}.wav'
            subprocess.run(['say', '-v', voice, '-o', str(aiff), text], check=True,
                           stdout=subprocess.DEVNULL)
            subprocess.run([str(converter), '--convert-audio', str(aiff), str(wav)],
                           check=True, stdout=subprocess.DEVNULL)
            with wave.open(str(wav), 'rb') as audio:
                if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                    raise ValueError('Unexpected rendered audio format')
                pcm = audio.readframes(audio.getnframes())
            if not pcm:
                raise ValueError(f'Voice {voice} rendered empty audio')
            clips.append(pcm)

    rng = random.Random(seed)
    target_frames = int(seconds * 16000)
    frames = 0
    turns = []
    expected = []
    with wave.open(str(out), 'wb') as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(16000)
        while frames < target_frames:
            for index in range(len(TURNS)):
                pcm = clips[index]
                speech_frames = len(pcm) // 2
                pause_frames = int(rng.choice((1.0, 1.8, 2.8, 4.0)) * 16000)
                if frames + speech_frames + pause_frames > target_frames:
                    break
                start = frames
                destination.writeframesraw(pcm)
                frames += speech_frames
                turns.append({'start_ms': start * 1000 // 16000,
                              'end_ms': frames * 1000 // 16000,
                              'voice': TURNS[index][0], 'text': TURNS[index][1]})
                expected.append(TURNS[index][1])
                destination.writeframesraw(bytes(pause_frames * 2))
                frames += pause_frames
            else:
                continue
            break
        if frames < target_frames:
            destination.writeframesraw(bytes((target_frames - frames) * 2))
    manifest = {'kind': 'synthetic_interview_fixture', 'duration_seconds': seconds,
                'sample_rate': 16000, 'seed': seed, 'turn_count': len(turns),
                'turns': turns, 'expected_text': ' '.join(expected),
                'limitations': 'Rendered, non-overlapping scripted speech; not a human interview or independent speech-end annotation.'}
    write_json(out.with_suffix('.manifest.json'), manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({k: v for k, v in make_fixture(args.out, args.seconds).items()
                      if k not in ('turns', 'expected_text')}, indent=2))
