"""Acceptance latency requires externally annotated speech boundaries."""
from .metrics import percentile

def annotated_latency(events,annotations,tolerance_ms=250):
    rows=[]
    for annotation in annotations:
        identity=annotation['segment_id'];start=annotation['speech_start_ms'];end=annotation['speech_end_ms']
        if start<0 or end<start:raise ValueError('Invalid speech annotation')
        candidates=sorted((e for e in events if e['segment_id']==identity and e.get('text','').strip()
                           and e['arrival_ms']>=start),key=lambda e:e['arrival_ms'])
        partial=next((e for e in candidates if e['state'] in ('partial','final')),None)
        finals=[e for e in candidates if e['state'] in ('final','correction') and e['end_ms']>=end-tolerance_ms and e['arrival_ms']>=end]
        rows.append({'segment_id':identity,'first_text_ms':partial['arrival_ms']-start if partial else None,
                     'final_after_speech_end_ms':finals[0]['arrival_ms']-end if finals else None,
                     'cold_start':annotation.get('cold_start',False)})
    eligible=[r for r in rows if not r['cold_start']]
    first=[r['first_text_ms'] for r in eligible if r['first_text_ms'] is not None]
    final=[r['final_after_speech_end_ms'] for r in eligible if r['final_after_speech_end_ms'] is not None]
    complete=bool(eligible) and len(first)==len(final)==len(eligible)
    return {'utterances':rows,'eligible_utterances':len(eligible),'missing_first_text':len(eligible)-len(first),
            'missing_final':len(eligible)-len(final),'first_text_p95_ms':percentile(first,95) if first else None,
            'final_p95_ms':percentile(final,95) if final else None,'coverage_complete':complete,
            'gate_passed':complete and percentile(first,95)<=2000 and percentile(final,95)<=2000,
            'limitations':'Speech annotations must be independent of recognizer timestamps. Cold-start exclusions are explicit; missing finals fail coverage.'}
