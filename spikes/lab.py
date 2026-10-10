"""Offline replay, measurement and native experiment report commands."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import tempfile
import time

from .core import ContextStore, Segment
from .metrics import percentile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'spikes/fixtures/episodes.json'


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload=json.dumps(data,indent=2,ensure_ascii=False)+'\n'
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()


def fixture_store():
    data = json.loads(FIXTURE.read_text())
    store = ContextStore()
    store.start('synthetic', 'meeting')
    from .core import SourceRef
    store.register_source('synthetic','meeting',SourceRef('shared-document','document','Shared document'))
    for row in data['segments']:
        store.ingest(Segment(tenant='synthetic', session='meeting', revision=0,
                             origin_id='shared-document' if row['id']=='untrusted' else 'meeting', **row))
    store.ingest(Segment(tenant='synthetic', session='meeting', **data['correction']), correction=True)
    return data, store


def replay() -> dict:
    data, store = fixture_store()
    try:
        checks = []
        for case in data['retrieval_cases']:
            evidence = store.retrieve('synthetic', 'meeting', case['query'])
            ids = [e.id for e in evidence]
            passed = case['expected_id'] in ids if case['expected_id'] else not ids
            snap = store.freeze('synthetic', 'meeting', case['id'], case['query'])
            checks.append({'case': case['id'], 'passed': passed, 'retrieved_ids': ids,
                           'context_utf8_bytes': snap.utf8_bytes,
                           'heuristic_context_tokens': snap.estimated_tokens})
        return {'kind': 'synthetic_context_replay', 'dataset': data['dataset'],
                'claims': 'Retrieval and context mechanics only; no LLM answers or speech recognition.',
                'cases': checks, 'passed': all(c['passed'] for c in checks),
                'speech_accuracy_measured': False, 'answer_quality_measured': False}
    finally:
        store.close()


def report() -> dict:
    # Synthetic timestamps simulate a long meeting. Execution is an accelerated replay.
    with tempfile.TemporaryDirectory(prefix='crackit-replay-') as directory:
        db_path = Path(directory) / 'replay.sqlite3'
        store = ContextStore(str(db_path))
        store.start('synthetic', 'long-meeting')
        ingest = []
        started = time.perf_counter()
        owner = Segment('launch-owner', 'synthetic', 'long-meeting', 0, 0, 4000,
                        'The Orion launch approver is Mira; approved budget is twelve thousand dollars.')
        store.ingest(owner)
        for index in range(1800):
            start_ms = index * 6000 + 5000
            text = 'Routine workstream %d status update. No change to the schedule or launch approver.' % (index % 30)
            before = time.perf_counter()
            store.ingest(Segment('turn-%04d' % index, 'synthetic', 'long-meeting', 0,
                                  start_ms, start_ms + 4500, text,
                                  source='mic' if index % 2 else 'system'))
            ingest.append((time.perf_counter() - before) * 1000)
        store.ingest(replace(owner, revision=1, text='The Orion launch approver is Mira; approved budget is ten thousand dollars.'), correction=True)
        timings, sizes, hits = [], [], []
        for index in range(200):
            snap = store.freeze('synthetic', 'long-meeting', 'request-%d' % index,
                                'What is the approved Orion budget and who is the launch approver?')
            timings.append(snap.elapsed_ms); sizes.append(snap.utf8_bytes)
            hits.append(any(e.id == 'launch-owner' and e.revision == 1 for e in snap.evidence))
        result = {'kind': 'offline_feasibility_measurement',
                  'generated_at': datetime.now(timezone.utc).isoformat(),
                  'environment': {'os': platform.platform(), 'architecture': platform.machine(),
                                  'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
                  'synthetic_meeting_hours': 3, 'segments': 1801, 'snapshot_samples': len(timings),
                  'replay_wall_seconds': time.perf_counter() - started,
                  'ingest_ms': {'p50': percentile(ingest, 50), 'p95': percentile(ingest, 95)},
                  'snapshot_ms': {'p50': percentile(timings, 50), 'p95': percentile(timings, 95)},
                  'max_context_utf8_bytes': max(sizes), 'context_byte_limit': 5400,
                  'corrected_old_evidence_retrieved': sum(hits),
                  'db_bytes': db_path.stat().st_size,
                  'process_max_rss_raw': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'rss_unit': 'bytes on macOS, KiB on Linux; process high-water mark, not isolated engine allocation',
                  'limitations': ['Synthetic repeated text, not representative customer meetings',
                                  'Accelerated replay, not a three-hour thermal/capture test',
                                  'SQLite lexical retrieval only; no semantic model or reranker',
                                  'Context sizes use a heuristic; not provider-tokenizer validation',
                                  'Timing excludes capture, networking, transcription and model inference'],
                  'gates': {'old_corrected_evidence_in_all_snapshots': all(hits),
                            'context_bytes_bounded': max(sizes) <= 5400},
                  'small_fixture_replay': replay()}
        store.close()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['replay', 'report'])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = replay() if args.command == 'replay' else report()
    write_json(args.out, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if (args.command == 'replay' and not result['passed']) or (
        args.command == 'report' and (not all(result['gates'].values()) or not result['small_fixture_replay']['passed'])):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
