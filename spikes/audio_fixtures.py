"""Original synthetic fixtures and seeded degradations, no ambient capture."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import wave
from .lab import ROOT,write_json

def read_pcm(path):
    with wave.open(str(path),'rb') as w:
        if (w.getnchannels(),w.getframerate(),w.getsampwidth())!=(1,16000,2):raise ValueError('Expected PCM16 mono 16kHz')
        return w.readframes(w.getnframes())

def write_pcm(path,pcm):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)

def noise(pcm,seed=20261008,snr=10):
    samples=array.array('h',pcm);rng=random.Random(seed)
    rms=math.sqrt(sum(s*s for s in samples)/max(1,len(samples)));sigma=rms/(10**(snr/20))
    return array.array('h',(max(-32768,min(32767,round(s+rng.gauss(0,sigma)))) for s in samples)).tobytes()

def names():
    source=json.loads((ROOT/'spikes/fixtures/names.json').read_text());root=ROOT/'.cache/name-fixtures';root.mkdir(exist_ok=True)
    clips=[]
    for voice in ('Samantha','Tara'):
        for case in source['cases']:
            identity=voice.lower()+'-'+case['id'];aiff=root/(identity+'.aiff');wav=root/(identity+'.wav')
            if not wav.exists():
                text=root/(identity+'.txt');text.write_text(case['text'])
                subprocess.run(['say','-v',voice,'-r','175','-o',str(aiff),'-f',str(text)],check=True)
                subprocess.run([str(ROOT/'.build/CrackitProbe.app/Contents/MacOS/CrackitProbe'),'--convert-audio',str(aiff),str(wav)],check=True,capture_output=True)
            pcm=read_pcm(wav)
            clips.append({**case,'id':identity,'voice':voice,'wav':str(wav.relative_to(ROOT)),
                          'audio_seconds':len(pcm)/32000,'sha256':hashlib.sha256(wav.read_bytes()).hexdigest()})
    write_json(root/'manifest.json',{'dataset':source['dataset'],'vocabulary':source['vocabulary'],'clips':clips,'limitations':source['limitations']})
    print('Prepared 24 synthetic name clips.')

def sustained():
    root=ROOT/'spikes/results/local';clean=read_pcm(root/'controlled.wav');other=read_pcm(root/'controlled-tara.wav')
    overlapping=array.array('h',clean);second=array.array('h',other)
    for i in range(min(len(overlapping),len(second))):overlapping[i]=max(-32768,min(32767,(overlapping[i]+second[i])//2))
    # Continuous speech exercises forced window boundaries, then silence,
    # seeded noise and overlap. This is a stress replay, not a real meeting.
    continuous=clean*4
    blocks=[continuous,b'\0'*32000*3,clean,b'\0'*32000*2,noise(other),b'\0'*32000*2,overlapping.tobytes(),b'\0'*32000*3]
    cycle=b''.join(blocks);duration_bytes=1800*32000
    pcm=(cycle*(duration_bytes//len(cycle)+1))[:duration_bytes]
    write_pcm(root/'sustained-30m.wav',pcm)
    write_json(root/'sustained-30m-manifest.json',{'duration_seconds':1800,'sha256':hashlib.sha256(pcm).hexdigest(),
        'cycle_seconds':len(cycle)/32000,'continuous_block_seconds':len(continuous)/32000,
        'provenance':'Original fictional TTS; seed 20261008, Gaussian noise target global SNR 10dB, 50/50 overlap mix. No accuracy/meeting representativeness claim.'})
    print('Prepared 30-minute controlled stress replay.')

def continuous():
    root=ROOT/'spikes/results/local';clean=read_pcm(root/'controlled.wav')
    write_pcm(root/'continuous-clean.wav',clean*4+b'\0'*32000*3)
    print('Prepared four-repeat continuous development fixture with three seconds of silence.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['names','sustained','continuous']);a=p.parse_args()
    {'names':names,'sustained':sustained,'continuous':continuous}[a.command]()
