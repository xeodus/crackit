"""Per-source bounded decoder transport with explicit epoch reset on overload."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from .lab import ROOT
from .streaming import TranscriptEvent

class LocalDecoder:
    def __init__(self,source,epoch,start_ms,model,vocabulary,folder,on_event,worker_version='v2'):
        if worker_version not in ('v1','v2'):raise ValueError('Unknown worker version')
        self.source=source;self.epoch=epoch;self.offset=start_ms;self.on_event=on_event
        self.queue=queue.Queue(maxsize=62);self.closed=threading.Event();self.ready=threading.Event();self.errors=[]
        self.max_queue_chunks=0;self.summary=None
        self.timing={'write_count':0,'max_write_ms':0.0,'max_queue_age_ms':0.0,
                     'max_read_interval_ms':0.0,'read_count':0,'last_read':None}
        self.timing_incidents=[]
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        self.log=(folder/('%s-%d.stderr.txt'%(source,epoch))).open('w')
        executable='.build/whisper-stream-v2' if worker_version=='v2' else '.build/whisper-stream'
        self.process=subprocess.Popen([str(ROOT/executable),str(ROOT/('.cache/whisper.cpp/models/ggml-'+model+'.bin')),
            str(ROOT/'.cache/whisper.cpp/models/ggml-silero-v6.2.0.bin'),'-',', '.join(vocabulary)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log)
        self.writer=threading.Thread(target=self._write,daemon=True);self.reader=threading.Thread(target=self._read,daemon=True)
        self.writer.start();self.reader.start()
        if worker_version=='v2' and not self.ready.wait(timeout=30):
            self.abort()
            raise RuntimeError('Decoder did not become ready within 30 seconds')
    def start_at(self,start_ms):
        if start_ms<0:raise ValueError('Invalid source start')
        self.offset=start_ms
    def _write(self):
        try:
            while not self.closed.is_set():
                try:item=self.queue.get(timeout=.1)
                except queue.Empty:continue
                if item is None:break
                pcm,queued_at=item
                now=time.monotonic()
                self.timing['max_queue_age_ms']=max(self.timing['max_queue_age_ms'],(now-queued_at)*1000)
                self.process.stdin.write(pcm);self.process.stdin.flush()
                self.timing['write_count']+=1
                write_ms=(time.monotonic()-now)*1000
                self.timing['max_write_ms']=max(self.timing['max_write_ms'],write_ms)
                if (write_ms>100 or (now-queued_at)*1000>100) and len(self.timing_incidents)<200:
                    self.timing_incidents.append({'at_monotonic':now,'write_ms':write_ms,
                        'queue_age_ms':(now-queued_at)*1000,'queue_chunks':self.queue.qsize()})
        except (OSError,ValueError):
            if not self.closed.is_set():self.errors.append('Decoder input transport failed')
        finally:
            try:self.process.stdin.close()
            except (OSError,ValueError):pass
    def _read(self):
        try:
            for line in self.process.stdout:
                now=time.monotonic()
                if self.timing['last_read'] is not None:
                    self.timing['max_read_interval_ms']=max(self.timing['max_read_interval_ms'],
                        (now-self.timing['last_read'])*1000)
                self.timing['last_read']=now
                self.timing['read_count']+=1
                raw=json.loads(line)
                if raw['type']=='ready':self.ready.set();continue
                if raw['type']=='summary':self.summary=raw;continue
                event=TranscriptEvent(self.source,self.epoch,'%s:%d:%s'%(self.source,self.epoch,raw['segment_id']),
                    raw['revision'],max(0,self.offset+int(raw['start_ms'])),max(0,self.offset+int(raw['end_ms'])),
                    raw['type'],raw['text'],raw['reason'])
                if not self.closed.is_set():self.on_event(event)
        except Exception as error:
            if not self.closed.is_set():self.errors.append(type(error).__name__)
    def submit(self,pcm):
        if self.process.poll() is not None:raise RuntimeError('Decoder stopped unexpectedly')
        try:
            self.queue.put_nowait((pcm,time.monotonic()))
            self.max_queue_chunks=max(self.max_queue_chunks,self.queue.qsize())
            return True
        except queue.Full:return False
    def finish(self):
        self.queue.put(None,timeout=120);self.writer.join(timeout=120)
        self.process.wait(timeout=120);self.reader.join(timeout=5)
        self.closed.set();self.process.stdout.close();self.log.close()
        if self.process.returncode or self.errors:raise RuntimeError('Decoder epoch incomplete')
    def abort(self):
        self.closed.set()
        if self.process.poll() is None:self.process.terminate()
        try:self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.writer.join(timeout=2);self.reader.join(timeout=2);self.process.stdout.close();self.log.close()

class SourceRouter:
    """Factory signature: (source, epoch, start_ms, callback) -> decoder.

    Timestamped PCM frames are at most 32 ms. System and microphone epochs
    are independent. Late callbacks from an aborted epoch are rejected.
    on_event runs on reader threads and must enqueue without blocking; the
    consumer applies events to SQLite on its owning thread. Finish follows
    producer shutdown, so no new feed calls may race with it.
    """
    def __init__(self,factory,on_event):
        self.factory=factory;self.on_event=on_event;self.sources={};self.lock=threading.RLock()
        self.retired_epochs=[]
        self.feed_locks={source:threading.RLock() for source in ('system','mic')}
    def _open(self,source,epoch,start_ms,prepared=False):
        state={'epoch':epoch,'start':start_ms,'expected':start_ms,'last_final':start_ms,
               'decoder':None,'prepared':prepared}
        with self.lock:self.sources[source]=state
        def callback(event):
            with self.lock:
                if self.sources.get(source) is not state:return
                if event.state in ('final','correction'):state['last_final']=max(state['last_final'],event.end_ms)
                self.on_event(event)
        try:state['decoder']=self.factory(source,epoch,start_ms,callback)
        except Exception:
            with self.lock:
                if self.sources.get(source) is state:self.sources.pop(source)
            raise
        return state
    def prepare(self,source):
        if source not in self.feed_locks:raise ValueError('Unknown source')
        with self.feed_locks[source]:
            with self.lock:
                if source in self.sources:return
            self._open(source,0,0,prepared=True)
    def feed(self,source,start_ms,pcm):
        if source not in ('system','mic') or len(pcm)%2 or not 0<len(pcm)<=1024 or start_ms<0:
            raise ValueError('Expected <=32ms PCM16 source frame')
        with self.feed_locks[source]:self._feed(source,start_ms,pcm)
    def _feed(self,source,start_ms,pcm):
        with self.lock:state=self.sources.get(source)
        if state is None:state=self._open(source,0,start_ms)
        if state['prepared']:
            state['start']=state['expected']=state['last_final']=start_ms
            state['decoder'].start_at(start_ms)
            state['prepared']=False
        if abs(start_ms-state['expected'])>2:
            self.reset(source,start_ms,'timestamp_discontinuity');state=self.sources[source]
        accepted=state['decoder'].submit(pcm)
        end=start_ms+len(pcm)*1000//32000
        if not accepted:
            self.reset(source,end,'decoder_queue_overload')
        else:state['expected']=end
    def reset(self,source,end_ms,reason):
        if source not in self.feed_locks or end_ms<0 or not reason:raise ValueError('Invalid source reset')
        with self.feed_locks[source]:self._reset(source,end_ms,reason)
    def _reset(self,source,end_ms,reason):
        reset_started=time.monotonic()
        with self.lock:
            state=self.sources.pop(source,None)
            if state is None:return
            gap=TranscriptEvent(source,state['epoch'],'%s:%d:gap'%(source,state['epoch']),0,
                                  min(state['last_final'],end_ms),max(state['expected'],end_ms),'gap',reason=reason)
            self.on_event(gap)
        state['decoder'].abort()
        retired={'source':source,'epoch':state['epoch'],'reason':reason,
            'pid':getattr(getattr(state['decoder'],'process',None),'pid',None),
            'max_queue_chunks':getattr(state['decoder'],'max_queue_chunks',None),
            'at_monotonic':reset_started,
            'timing_incidents':getattr(state['decoder'],'timing_incidents',[]),
            'timing':{k:v for k,v in getattr(state['decoder'],'timing',{}).items() if k!='last_read'}}
        self.retired_epochs.append(retired)
        with self.lock:self._open(source,state['epoch']+1,end_ms)
        retired['reset_ms']=(time.monotonic()-reset_started)*1000
    def finish(self):
        failures=[]
        for source,state in list(self.sources.items()):
            try:state['decoder'].finish()
            except Exception:
                state['decoder'].abort();failures.append(source)
                self.on_event(TranscriptEvent(source,state['epoch'],'%s:%d:finish-gap'%(source,state['epoch']),0,
                    min(state['last_final'],state['expected']),state['expected'],'gap',reason='decoder_finish_failure'))
        if failures:raise RuntimeError('One or more source epochs did not finish')
    def abort(self):
        with self.lock:
            states=list(self.sources.values());self.sources.clear()
        for state in states:
            state['decoder'].abort()

def local_router(folder,on_event,model='base.en',vocabulary=(),worker_version='v2'):
    return SourceRouter(lambda source,epoch,start,callback:LocalDecoder(source,epoch,start,model,vocabulary,folder,callback,worker_version),on_event)
