"""Controlled end-to-end per-source reset probe. No ambient audio or API calls."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import queue
import time
from .audio_fixtures import read_pcm
from .core import ContextStore
from .lab import ROOT,write_json
from .streaming import apply_event,EvidenceGate
from .transport import local_router

def run(out,worker_version='v2'):
    pcm=read_pcm(ROOT/'spikes/results/local/controlled.wav')
    first=pcm[:5*32000];second=pcm
    incoming=queue.Queue();events=[];errors=[]
    router=local_router(out.parent/(out.stem+'-logs'),incoming.put,worker_version=worker_version)
    store=ContextStore();store.start('probe','meeting')
    trace=out.with_suffix('.events.jsonl').open('w');origin=time.perf_counter()
    def drain():
        while True:
            try:event=incoming.get_nowait()
            except queue.Empty:break
            apply_event(store,'probe','meeting',event)
            record={**asdict(event),'arrival_ms':(time.perf_counter()-origin)*1000}
            events.append(record);trace.write(json.dumps(record)+'\n');trace.flush()
    try:
        second_offset=7008
        end_ms=second_offset+len(second)/32
        for clock in range(0,int(end_ms)+1,32):
            deadline=origin+clock/1000
            if deadline>time.perf_counter():time.sleep(deadline-time.perf_counter())
            if clock<5000:
                frame=first[clock*32:(clock+32)*32]
                router.feed('system',clock,frame)
            elif clock>=second_offset:
                index=(clock-second_offset)*32;frame=second[index:index+1024]
                if frame:router.feed('system',clock,frame)
            router.feed('mic',clock,b'\0'*1024);drain()
        router.finish();drain()
        snapshot=store.freeze('probe','meeting','budget','approved budget')
        gate=EvidenceGate();gate.begin(snapshot,store)
        result={'status':'completed','worker_version':worker_version,'events':events,'gaps':store.gaps('probe','meeting'),
                'source_epochs':{s:v['epoch'] for s,v in router.sources.items()},
                'isolation_gate_passed':router.sources['mic']['epoch']==0 and router.sources['system']['epoch']==1,
                'final_transcript':' '.join(r['text'].strip() for r in store.transcript('probe','meeting') if r['state']=='final'),
                'snapshot_evidence':[e.id for e in snapshot.evidence],
                'answer_gate_accepts_current_evidence':gate.accepts('budget',store),
                'wall_seconds':time.perf_counter()-origin,
                'limitations':'Controlled PCM and silent microphone, not native live capture; no independent speech-end annotations, so no latency acceptance claim.'}
        write_json(out,result);return result
    except Exception as error:
        errors.append(type(error).__name__)
        for state in list(router.sources.values()):state['decoder'].abort()
        drain();write_json(out,{'status':'incomplete','errors':errors,'events':events});raise
    finally:trace.close();store.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'spikes/results/local/router-probe.json')
    result=run(p.parse_args().out);print(json.dumps({k:v for k,v in result.items() if k!='events'},indent=2))
