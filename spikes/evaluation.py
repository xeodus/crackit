"""Frozen, resumable recognition comparisons. No tuning on held-out output."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from .lab import ROOT,write_json
from .metrics import word_error_rate,percentile
from .audio_fixtures import read_pcm
from .streaming import replay,file_digest

CONFIG={'version':'reliability-v1','local_models':['base.en','small.en'],'backend':'cpu','threads':4,
        'language':'en','decoding':'greedy best_of=1 temperature_increment=0 timestamp tokens enabled',
        'conditions':['unbiased','vocabulary'],'vad':'silero-v6.2.0','speech_onset_ms':224,
        'silence_endpoint_ms':608,'padding_ms':300,'max_window_seconds':30,
        'decode_interval_ms':1000,'source_sha256':None,
        'acceptance':{'name_owner_accuracy':.95,'first_partial_p95_ms':2000,'endpoint_p95_ms':2000}}

def digest(path):return file_digest(path)

def freeze():
    manifests=[ROOT/'.cache/name-fixtures/manifest.json',ROOT/'.cache/vctk/manifest.json']
    missing=[str(p) for p in manifests if not p.exists()]
    if missing:raise ValueError('Prepare manifests first: '+', '.join(missing))
    out=ROOT/'spikes/results/local/frozen-evaluation.json'
    config={**CONFIG,'source_sha256':digest(ROOT/'spikes/native/stream_worker.cpp')}
    record={'created_at':datetime.now(timezone.utc).isoformat(),'config':config,
            'manifests':{str(p.relative_to(ROOT)):digest(p) for p in manifests},
            'model_sha256':{m:digest(ROOT/('.cache/whisper.cpp/models/ggml-'+m+'.bin')) for m in CONFIG['local_models']},
            'held_out_status':'Configuration frozen before recognizer evaluation; same declared models/conditions used for both splits.'}
    if out.exists():
        prior=json.loads(out.read_text())
        if any(prior[k]!=record[k] for k in ('config','manifests','model_sha256')):
            raise ValueError('Frozen configuration changed; create a new evaluation version rather than overwrite')
    else:write_json(out,record)
    print('Frozen configuration: '+str(out))

def number_normalized(text):
    # Explicit narrow English amount normalization; raw WER remains available.
    text=text.casefold()
    for spoken,value in (('twelve thousand dollars','12000'),('fifteen thousand dollars','15000')):
        text=text.replace(spoken,value)
    text=re.sub(r'\$([\d,]+)',lambda m:m.group(1).replace(',',''),text)
    return text

def owner_from_text(text):
    matches=re.findall(r'\b([^\W\d_]+)\s+owns\b',text,re.IGNORECASE)
    if re.search(r'owner\s+(?:is\s+)?(?:still\s+)?undecided',text,re.IGNORECASE):return None
    return matches[-1] if matches else None

def score(clip,hypothesis,vocabulary):
    result={'raw_wer':word_error_rate(clip['text'],hypothesis),
            'number_normalized_wer':word_error_rate(number_normalized(clip['text']),number_normalized(hypothesis)),
            'number_normalization_note':'Only explicit twelve/fifteen thousand dollar examples and dollar numerals; not a general number normalizer.'}
    if 'mentions' in clip:
        from dataclasses import asdict
        from .name_review import review_name
        recognized=[name for name in clip['mentions'] if re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',hypothesis,re.IGNORECASE)]
        predicted_owner=owner_from_text(hypothesis)
        result.update({'expected_names':clip['mentions'],'exact_names_found':recognized,
                       'name_correct':len(recognized),'name_total':len(clip['mentions']),
                       'expected_owner':clip['owner'],'parsed_owner':predicted_owner,
                       'owner_entity_review':asdict(review_name(predicted_owner,vocabulary)) if predicted_owner else None,
                       'owner_correct':(predicted_owner or '').casefold()==(clip['owner'] or '').casefold(),
                       'unexpected_roster_names':[n for n in vocabulary if n not in clip['mentions'] and re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',hypothesis,re.IGNORECASE)],
                       'owner_metric_note':'Conservative literal pattern scorer; semantic human review required for unclear grammar/negation.'})
    return result

def local_whole(clip,model,vocabulary,destination):
    prefix=destination.with_suffix('')
    command=[str(ROOT/'.cache/whisper.cpp/build/bin/whisper-cli'),'-m',str(ROOT/('.cache/whisper.cpp/models/ggml-'+model+'.bin')),
             '-f',str(ROOT/clip['wav']),'-ng','-t','4','-l','en','-bs','1','-bo','1','-nf','-oj','-of',str(prefix)]
    if vocabulary:command+=['--prompt',', '.join(vocabulary)]
    started=time.perf_counter();result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    destination.with_suffix('.stderr.txt').write_text(result.stderr)
    if result.returncode:raise RuntimeError('Recognizer failed; inspect local log')
    data=json.loads(Path(str(prefix)+'.json').read_text());text=' '.join(t['text'].strip() for t in data.get('transcription',[]))
    return {'text':text,'wall_seconds':time.perf_counter()-started,'mode':'whole_file_includes_startup','model':model,
            'runtime_config_note':'Whole-file CLI uses segment timestamps; token timestamps and VAD apply to the separate streaming worker.',
            'timing_acceptance_eligible':False}

def validate_frozen():
    p=ROOT/'spikes/results/local/frozen-evaluation.json'
    if not p.exists():raise ValueError('Freeze the evaluation before running it')
    frozen=json.loads(p.read_text())
    if digest(ROOT/'spikes/native/stream_worker.cpp')!=frozen['config']['source_sha256']:raise ValueError('Decoder source differs from frozen configuration')
    for path,expected in frozen['manifests'].items():
        if digest(ROOT/path)!=expected:raise ValueError('Frozen fixture manifest changed')
    for model,expected in frozen['model_sha256'].items():
        if digest(ROOT/('.cache/whisper.cpp/models/ggml-'+model+'.bin'))!=expected:
            raise ValueError('Frozen model changed')
    return frozen

def run(args):
    frozen=validate_frozen();names=json.loads((ROOT/'.cache/name-fixtures/manifest.json').read_text())
    corpus=json.loads((ROOT/'.cache/vctk/manifest.json').read_text())
    clips=names['clips']+corpus['clips'];vocabulary=names['vocabulary']
    clips=[c for c in clips if c['split']==args.split and (args.dataset=='both' or ('voice' in c)==(args.dataset=='names'))]
    out=ROOT/'spikes/results/local/evaluation';out.mkdir(exist_ok=True)
    failures=[]
    for clip in clips:
        if digest(ROOT/clip['wav'])!=clip['sha256']:raise ValueError('Audio fixture changed')
        for condition in frozen['config']['conditions']:
            terms=vocabulary if condition=='vocabulary' else []
            for model in (frozen['config']['local_models'] if args.engine=='local' else [args.engine]):
                identity=clip['id']+'-'+model+'-'+condition+'-'+args.mode
                destination=out/(identity+'.result.json')
                if destination.exists():
                    prior=json.loads(destination.read_text())
                    if (prior['fixture_sha256']!=clip['sha256'] or prior['clip_id']!=clip['id']
                            or prior['config_digest']!=digest(ROOT/'spikes/results/local/frozen-evaluation.json')
                            or prior['result'].get('status') not in (None,'completed')):
                        raise ValueError('Saved recognition is incomplete or has different provenance; do not silently reuse or retry')
                    continue
                try:
                    if args.engine=='assemblyai':
                        from .providers import assembly_stt,credentials,configured_ledger
                        ledger=configured_ledger()
                        try:result=assembly_stt(ROOT/clip['wav'],clip['text'],credentials()['ASSEMBLYAI_API_KEY'],ledger,terms,
                                               failure_trace_path=out/(identity+'.transport-failure.json'))
                        finally:ledger.close()
                        write_json(out/(identity+'.provider.json'),result)
                        if result['status']!='completed':raise RuntimeError('Hosted session incomplete; retained reservation')
                        text=result['transcript']
                    elif args.mode=='stream':
                        result=replay(ROOT/clip['wav'],model,terms,True,out/(identity+'.stream.json'));text=result['transcript']
                        if result['status']!='completed':raise RuntimeError('Streaming replay incomplete')
                    else:
                        result=local_whole(clip,model,terms,out/(identity+'.recognizer.json'));text=result['text']
                    record={'clip_id':clip['id'],'speaker':clip.get('speaker',clip.get('voice')),'accent':clip.get('accent','synthetic'),
                            'split':args.split,'condition':condition,'fixture_sha256':clip['sha256'],
                            'config_digest':digest(ROOT/'spikes/results/local/frozen-evaluation.json'),
                            'result':result,'score':score(clip,text,vocabulary)}
                    write_json(destination,record);print('Scored '+identity,flush=True)
                except Exception as error:
                    failures.append({'id':identity,'error_type':type(error).__name__})
                    write_json(out/(identity+'.failure.json'),failures[-1]);print('Stopped on '+identity+' ('+type(error).__name__+')',flush=True)
                    if args.engine=='assemblyai':write_json(ROOT/'spikes/results/local/benchmark-halt.json',failures[-1])
                    # No automatic retries or continuing after a billing/transport failure.
                    raise RuntimeError('Evaluation incomplete; inspect saved failure record') from None

def report():
    records=[json.loads(p.read_text()) for p in (ROOT/'spikes/results/local/evaluation').glob('*.result.json')]
    groups={}
    for row in records:
        r=row['result'];engine=r.get('model','assemblyai');kind='names' if 'name_total' in row['score'] else 'vctk'
        key='|'.join([row['split'],kind,engine,row['condition'],r.get('mode','stream')]);groups.setdefault(key,[]).append(row)
    summary={}
    for key,rows in groups.items():
        edits=sum(r['score']['raw_wer']['edits'] for r in rows);words=sum(r['score']['raw_wer']['reference_words'] for r in rows)
        total_names=sum(r['score'].get('name_total',0) for r in rows)
        summary[key]={'samples':len(rows),'raw_wer':edits/words if words else None,
                      'reference_words':words,'word_edits':edits,
                      'name_accuracy':sum(r['score'].get('name_correct',0) for r in rows)/total_names if total_names else None,
                      'owner_accuracy':sum(r['score'].get('owner_correct',0) for r in rows)/len(rows) if total_names else None,
                      'false_roster_substitutions':sum(len(r['score'].get('unexpected_roster_names',[])) for r in rows)}
        expected=12 if total_names else 72
        summary[key]['expected_samples']=expected
        summary[key]['coverage_complete']=len(rows)==expected
        summary[key]['name_owner_gate_passed']=(len(rows)==expected and total_names>0
             and summary[key]['name_accuracy']>=.95 and summary[key]['owner_accuracy']>=.95
             and summary[key]['false_roster_substitutions']==0) if total_names else None
        accents={}
        for row in rows:
            accent=row['accent'];a=accents.setdefault(accent,{'samples':0,'edits':0,'reference_words':0,'speakers':set()})
            a['samples']+=1;a['edits']+=row['score']['raw_wer']['edits'];a['reference_words']+=row['score']['raw_wer']['reference_words'];a['speakers'].add(row['speaker'])
        summary[key]['accents']={accent:{'samples':a['samples'],'speakers':len(a['speakers']),
            'raw_wer':a['edits']/a['reference_words'] if a['reference_words'] else None} for accent,a in accents.items()}
    folder=ROOT/'spikes/results/local/evaluation'
    failures=[json.loads(p.read_text()) for p in folder.glob('*.failure.json') if not p.with_name(p.name.replace('.failure.json','.result.json')).exists()]
    result={'groups':summary,'record_count':len(records),'acceptance_targets':CONFIG['acceptance'],
            'unresolved_failures':failures,
            'hosted_halted':(ROOT/'spikes/results/local/benchmark-halt.json').exists(),
            'limitations':'Read speech and synthetic owners; not conversational ground truth. Count and split coverage must be checked before declaring a gate passed.'}
    write_json(ROOT/'spikes/results/local/evaluation-summary.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run','report'])
    p.add_argument('--split',choices=['development','held_out'],default='development')
    p.add_argument('--dataset',choices=['names','vctk','both'],default='both')
    p.add_argument('--engine',choices=['local','assemblyai'],default='local')
    p.add_argument('--mode',choices=['whole','stream'],default='whole');a=p.parse_args()
    if a.command=='freeze':freeze()
    elif a.command=='report':report()
    else:run(a)
