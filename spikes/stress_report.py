"""Report resource/transport gates without converting timestamp proxies to latency proof."""
import argparse
from collections import Counter
import json
from pathlib import Path
from .lab import ROOT,write_json

def analyze(path,accuracy_check=None):
    data=json.loads(Path(path).read_text());events=data.get('events',[]);summary=data.get('summary',{})
    worker_gaps=[e for e in events if e['type']=='gap']
    complete=(data['status']=='completed' and abs(summary.get('audio_seconds',0)-data['audio_seconds'])<.1)
    duration_gate=complete and data['audio_seconds']>=1800
    max_audio=summary.get('max_audio_samples');max_queue=data.get('max_queue_samples')
    finals=[e for e in events if e['type']=='final' and e.get('text','').strip()]
    duplicates=[identity for identity,count in Counter(e['segment_id'] for e in finals).items() if count>1]
    gaps=data.get('gaps',[])+worker_gaps
    result={'status':data['status'],'audio_seconds':data['audio_seconds'],'wall_seconds':data['wall_seconds'],
            'duration_gate_passed':duration_gate,'max_retained_audio_seconds':max_audio/16000 if max_audio is not None else None,
            'max_input_queue_seconds':max_queue/16000 if max_queue is not None else None,
            'buffer_gate_passed':max_audio is not None and max_queue is not None and max_audio<=480000 and max_queue<=32000,
            'gaps':gaps,'errors':data.get('errors',[]),'final_segments':len(finals),'duplicate_final_segment_ids':duplicates,
            'rolling_boundaries':sum(e.get('reason')=='window_boundary' for e in finals),
            'transport_gate_passed':complete and not gaps and not duplicates and not data.get('errors'),
            'latency_gate':'unmeasured: no independent speech-end annotations',
            'accuracy_gate':'unmeasured: stress audio is repeated TTS, noise and overlap without word-aligned ground truth',
            'limitations':'Queue bound excludes kernel pipe buffers and model memory. One-source synthetic PCM replay; native capture and dual-decoder capacity remain separate.'}
    if accuracy_check:
        check=json.loads(Path(accuracy_check).read_text())
        if check['source_sha256']!=data['source_sha256']:raise ValueError('Accuracy check belongs to a different worker')
        result['development_continuity_check']=check['number_normalized_wer']
        if check['number_normalized_wer']['edits']:
            result['accuracy_gate']='failed: controlled initial block lost words despite transport completion; full meeting accuracy remains unmeasured'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--accuracy-check',type=Path)
    a=p.parse_args();r=analyze(a.input,a.accuracy_check);write_json(a.out,r);print(json.dumps(r,indent=2))
