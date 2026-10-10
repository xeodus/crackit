"""Provider-neutral revision events and paced, bounded on-device replay."""
import argparse
from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import wave
from .core import ContextStore, Segment
from .lab import ROOT,write_json
from .metrics import percentile

def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

@dataclass(frozen=True)
class TranscriptEvent:
    source: str
    epoch: int
    segment_id: str
    revision: int
    start_ms: int
    end_ms: int
    state: str
    text: str=''
    reason: str=''

    def __post_init__(self):
        if (self.source not in ('system','mic') or self.epoch<0 or self.revision<0
                or self.start_ms<0 or self.end_ms<self.start_ms
                or self.state not in ('partial','final','correction','gap') or not self.segment_id):
            raise ValueError('Invalid transcript event')

def apply_event(store,tenant,session,event):
    if event.state=='gap':
        store.discard_provisional(tenant,session,event.source,event.epoch)
        store.gap(tenant,session,event.start_ms,event.end_ms,event.reason or 'capture_gap');return
    store.ingest(Segment(event.segment_id,tenant,session,event.revision,event.start_ms,event.end_ms,
                         event.text,'final' if event.state=='correction' else event.state,event.source,event.epoch),
                 correction=event.state=='correction')

class EvidenceGate:
    """An unrelated partial need not cancel an answer; changed cited evidence does."""
    def __init__(self): self.request_id=None;self.references={};self.scope=None;self.fact_signature=None;self.baseline_valid=False
    def begin(self,snapshot,store):
        self.request_id=snapshot.request_id;self.scope=(snapshot.tenant,snapshot.session)
        self.baseline_valid=store.session(*self.scope)['version']==snapshot.version
        self.fact_signature=store.fact_signature(*self.scope)
        self.references={e.id:e.revision for e in snapshot.evidence}
    def cancel(self):self.request_id=None
    def accepts(self,request_id,store):
        if self.request_id!=request_id or self.scope is None or not self.baseline_valid:return False
        try:
            rows={r['id']:r['revision'] for r in store.transcript(*self.scope)}
            if store.fact_signature(*self.scope)!=self.fact_signature:return False
        except KeyError:return False
        return all(rows.get(identity)==revision for identity,revision in self.references.items())

def normalize_assembly_turn(event,source,epoch,revisions,finals):
    identity='%s:%d:turn-%s'%(source,epoch,event['turn_order'])
    text=event.get('transcript','')
    if text.strip() in ('[BLANK_AUDIO]','[SILENCE]','[NO_SPEECH]'):text=''
    fingerprint=(text,bool(event.get('end_of_turn')),
                 tuple((w.get('text'),w.get('start'),w.get('end')) for w in event.get('words',[])))
    prior=revisions.get(identity)
    if prior and prior[1]==fingerprint:return None
    # Late partials may not undo finals. Revised formatted finals are corrections.
    if identity in finals and not fingerprint[1]:return None
    revision=0 if prior is None else prior[0]+1
    revisions[identity]=(revision,fingerprint)
    state='partial'
    if fingerprint[1]:state='correction' if identity in finals else 'final';finals.add(identity)
    words=event.get('words',[])
    start=int(min((w['start'] for w in words),default=0));end=int(max((w['end'] for w in words),default=start))
    return TranscriptEvent(source,epoch,identity,revision,start,end,state,fingerprint[0])

class BoundedAudioQueue:
    def __init__(self,max_samples=32000):self.max_samples=max_samples;self.samples=0;self.items=[]
    def push(self,start_ms,pcm):
        if len(pcm)%2:raise ValueError('PCM frames require whole samples')
        count=len(pcm)//2
        if self.samples+count>self.max_samples:
            begin=self.items[0][0] if self.items else start_ms
            self.items=[];self.samples=0
            return (begin,start_ms+count*1000//16000)
        self.items.append((start_ms,pcm));self.samples+=count;return None
    def pop(self):
        item=self.items.pop(0);self.samples-=len(item[1])//2;return item

def replay(wav,model='base.en',vocabulary=(),paced=False,out=None,worker_version='v1'):
    if worker_version not in ('v1','v2'):raise ValueError('Unknown worker version')
    with wave.open(str(wav),'rb') as audio:
        if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth(),audio.getcomptype())!=(16000,1,2,'NONE'):
            raise ValueError('Expected 16kHz mono PCM WAV')
        duration=audio.getnframes()/16000
        if not 0<duration<=1800.1:raise ValueError('Replay limited to 30 minutes')
    executable='.build/whisper-stream' if worker_version=='v1' else '.build/whisper-stream-v2'
    worker_source='spikes/native/stream_worker.cpp' if worker_version=='v1' else 'spikes/native/stream_worker_v2.cpp'
    command=[str(ROOT/executable),str(ROOT/('.cache/whisper.cpp/models/ggml-'+model+'.bin')),
             str(ROOT/'.cache/whisper.cpp/models/ggml-silero-v6.2.0.bin'),'-',', '.join(vocabulary)]
    destination=Path(out) if out else ROOT/'spikes/results/local/stream.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Stderr is file-backed, preventing a full log pipe from blocking inference.
    log=destination.with_suffix('.stderr.txt').open('w')
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
    source_digest=file_digest(ROOT/worker_source)
    dependencies={'spikes/native/overlap_alignment.h':file_digest(ROOT/'spikes/native/overlap_alignment.h')} if worker_version=='v2' else {}
    event_file=destination.with_suffix('.events.jsonl').open('w')
    frames=queue.Queue(maxsize=62);events=[];gaps=[];errors=[];sent=[]
    origin=time.perf_counter();sample_clock=0;max_queue=0;epoch=0
    write_done=threading.Event()
    def writer():
        try:
            while True:
                item=frames.get()
                if item is None:break
                start_ms,pcm=item
                process.stdin.write(pcm);process.stdin.flush()
                sent.append({'start_ms':start_ms,'sent_at_ms':(time.perf_counter()-origin)*1000})
        except (BrokenPipeError,OSError) as error:errors.append(type(error).__name__)
        finally:
            try:process.stdin.close()
            except OSError:pass
            write_done.set()
    def reader():
        try:
            for line in process.stdout:
                event=json.loads(line);event['arrival_ms']=(time.perf_counter()-origin)*1000;events.append(event)
                if event['type']=='ready':events.pop();continue
                event_file.write(json.dumps(event)+'\n');event_file.flush()
        except Exception as error:errors.append(type(error).__name__)
    sending=threading.Thread(target=writer,daemon=True);reading=threading.Thread(target=reader,daemon=True)
    sending.start();reading.start()
    try:
        with wave.open(str(wav),'rb') as audio:
            while True:
                pcm=audio.readframes(512)
                if not pcm:break
                deadline=origin+sample_clock/16000
                if paced and deadline>time.perf_counter():time.sleep(deadline-time.perf_counter())
                try:frames.put((sample_clock*1000//16000,pcm),timeout=.05 if paced else 120)
                except queue.Full:
                    # Stop this epoch rather than silently dropping/compressing time.
                    gaps.append({'source':'system','epoch':epoch,'start_ms':max(0,sample_clock*1000//16000-2000),
                                 'end_ms':sample_clock*1000//16000,'reason':'decoder_queue_overload'})
                    process.terminate();errors.append('Queue overflow; source epoch terminated');break
                max_queue=max(max_queue,frames.qsize()*512)
                sample_clock+=len(pcm)//2
        if process.poll() is None and not errors:frames.put(None,timeout=120)
        write_done.wait(timeout=120);process.wait(timeout=120);reading.join(timeout=5)
    except Exception as error:
        errors.append(type(error).__name__)
    finally:
        if process.poll() is None:process.kill();process.wait()
        reading.join(timeout=5)
        process.stdout.close();log.close();event_file.close()
    store=ContextStore();store.start('replay','meeting');normalized=[]
    try:
        for event in events:
            if event['type']=='summary':continue
            normalized_event=TranscriptEvent('system',epoch,'system:%d:%s'%(epoch,event['segment_id']),event['revision'],
                max(0,int(event['start_ms'])),max(0,int(event['end_ms'])),event['type'],event['text'],event['reason'])
            apply_event(store,'replay','meeting',normalized_event);normalized.append(asdict(normalized_event))
        final_text=' '.join(r['text'].strip() for r in store.transcript('replay','meeting') if r['state']=='final' and r['text'].strip())
    finally:store.close()
    summary=next((e for e in events if e['type']=='summary'),{})
    final_delays=[max(0,e['arrival_ms']-e['end_ms']) for e in events if e['type']=='final' and e['text'].strip()] if paced else []
    result={'kind':'bounded_local_replay','model':model,'vocabulary':list(vocabulary),'paced':paced,
            'worker_version':worker_version,
            'fixture_sha256':file_digest(wav),'audio_seconds':duration,
            'source_sha256':source_digest,
            'dependency_sha256':dependencies,
            'events':events,'normalized_events':normalized,'gaps':gaps,'errors':errors,
            'transcript':final_text,'max_queue_samples':max_queue,'summary':summary,
            'wall_seconds':time.perf_counter()-origin,'returncode':process.returncode,
            'endpoint_delays_ms':final_delays,'endpoint_delay_note':'Recognized last-word time, including cold startup; annotated speech end is required for acceptance.',
            'status':'completed' if process.returncode==0 and not errors else 'incomplete'}
    write_json(destination,result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--wav',type=Path,required=True)
    parser.add_argument('--model',choices=['base.en','small.en'],default='base.en')
    parser.add_argument('--worker-version',choices=['v1','v2'],default='v1')
    parser.add_argument('--paced',action='store_true');parser.add_argument('--vocabulary',nargs='*',default=[])
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    result=replay(args.wav,args.model,args.vocabulary,args.paced,args.out,args.worker_version)
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','normalized_events')},indent=2))
