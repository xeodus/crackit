"""Fetch a reproducible VCTK subset using the publisher's ZIP byte ranges.

No provider calls. Rejects servers ignoring Range; never silently downloads 11GB.
Archive CRCs and clip SHA256 are checked; no full-archive SHA claim is made.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from .lab import ROOT,write_json

URL='https://datashare.ed.ac.uk/server/api/core/bitstreams/535f4286-e54c-4038-838c-a02285e32cb2/content'
CITATION='Yamagishi, Veaux, MacDonald (2019), CSTR VCTK Corpus 0.92, University of Edinburgh. doi:10.7488/ds/2645. CC BY 4.0.'

class RemoteZip(io.RawIOBase):
    def __init__(self,url,cache):
        self.url=url;self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=30) as r:
            if 'zip' not in r.headers.get('Content-Type',''):raise ValueError('Publisher did not return ZIP')
            self.size=int(r.headers['Content-Length']);self.etag=r.headers.get('ETag')
        identity=hashlib.sha256((url+str(self.etag)+str(self.size)).encode()).hexdigest()[:16]
        self.cache=self.cache/identity;self.cache.mkdir(exist_ok=True)
        self.position=0;self.downloaded=0;self.blocksize=1024*1024
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else (self.position+offset if whence==1 else self.size+offset)
        if self.position<0:raise ValueError('Negative seek')
        return self.position
    def read(self,n=-1):
        n=min(self.size-self.position,n if n>=0 else self.size-self.position)
        chunks=[]
        while n>0:
            block=self.position//self.blocksize;start=block*self.blocksize;end=min(start+self.blocksize,self.size)-1
            path=self.cache/str(block)
            if not path.exists():
                req=urllib.request.Request(self.url,headers={'Range':'bytes=%d-%d'%(start,end)})
                if self.etag:req.add_header('If-Range',self.etag)
                with urllib.request.urlopen(req,timeout=60) as r:
                    if r.status!=206 or r.headers.get('Content-Range')!='bytes %d-%d/%d'%(start,end,self.size):
                        raise ValueError('Server ignored archive range; refusing full download')
                    data=r.read(self.blocksize+1)
                    if len(data)!=end-start+1:raise ValueError('Incomplete archive range')
                self.downloaded+=len(data)
                if self.downloaded>400*1024*1024:raise ValueError('Subset transfer cap exceeded')
                temporary=path.with_suffix('.download')
                temporary.write_bytes(data);temporary.replace(path)
            data=path.read_bytes();offset=self.position-start;count=min(n,len(data)-offset)
            if count<=0:raise ValueError('Corrupt range cache')
            chunks.append(data[offset:offset+count]);self.position+=count;n-=count
        return b''.join(chunks)

def select_speakers(info,available):
    groups={}
    for line in info.splitlines():
        fields=line.split()
        if len(fields)<4 or not re.fullmatch(r'p?\d+',fields[0]):continue
        speaker=fields[0] if fields[0].startswith('p') else 'p'+fields[0]
        if speaker in available:groups.setdefault(fields[3],[]).append(speaker)
    accents=sorted(groups,key=lambda a:(not ('india' in a.lower()),a))
    selected=[];index=0
    while len(selected)<24:
        added=False
        for accent in accents:
            speakers=sorted(groups[accent])
            if index<len(speakers):selected.append((speakers[index],accent));added=True
            if len(selected)==24:break
        if not added:raise ValueError('Not enough annotated speakers')
        index+=1
    # Alternate within each accent where possible; balance remaining counts.
    splits={'development':[],'held_out':[]};seen={}
    for speaker,accent in selected:
        preferred='development' if seen.get(accent,0)%2==0 else 'held_out';seen[accent]=seen.get(accent,0)+1
        if len(splits[preferred])>=12:preferred='held_out' if preferred=='development' else 'development'
        splits[preferred].append((speaker,accent))
    return splits

def fetch():
    destination=ROOT/'.cache/vctk';destination.mkdir(parents=True,exist_ok=True)
    manifest=destination/'manifest.json'
    if manifest.exists():
        print('Frozen VCTK manifest already exists: '+str(manifest));return
    remote=RemoteZip(URL,destination/'ranges')
    with zipfile.ZipFile(remote) as archive:
        names=archive.namelist()
        speaker_file=next(n for n in names if n.endswith('speaker-info.txt'))
        info=archive.read(speaker_file).decode();(destination/'speaker-info.txt').write_text(info)
        available={re.search(r'(p\d+)_',n).group(1) for n in names
                   if n.endswith('_mic1.flac') and re.search(r'(p\d+)_',n) and '__MACOSX' not in n}
        splits=select_speakers(info,available)
        clips=[]
        for split,speakers in splits.items():
            for speaker,accent in speakers:
                candidates=sorted(n for n in names if re.search(r'/'+speaker+r'/'+speaker+r'_\d+_mic1\.flac$',n)
                                  and int(re.search(r'_(\d+)_mic1',n).group(1))>=25)
                count=0
                for name in candidates:
                    identity=Path(name).stem.removesuffix('_mic1')
                    text_name=next((n for n in names if n.endswith('/'+speaker+'/'+identity+'.txt')),None)
                    if not text_name:continue
                    text=archive.read(text_name).decode().strip()
                    if not text:continue
                    raw=archive.read(name);flac=destination/(identity+'.flac');flac.write_bytes(raw)
                    wav=destination/(identity+'.wav')
                    conversion=subprocess.run([str(ROOT/'.build/CrackitProbe.app/Contents/MacOS/CrackitProbe'),'--convert-audio',str(flac),str(wav)],capture_output=True,text=True,check=True)
                    metadata=json.loads(conversion.stdout)
                    if not 0<metadata['duration_seconds']<=30:continue
                    clips.append({'id':identity,'speaker':speaker,'accent':accent,'split':split,'text':text,
                                  'wav':str(wav.relative_to(ROOT)),'audio_seconds':metadata['duration_seconds'],
                                  'sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),'archive_crc32':archive.getinfo(name).CRC})
                    count+=1
                    if count==6:break
                if count!=6:raise ValueError('Speaker missing six eligible clips: '+speaker)
                print('Prepared '+speaker+' '+split,flush=True)
        write_json(manifest,{'dataset':'VCTK-0.92-subset-v1','citation':CITATION,'url':URL,'etag':remote.etag,
                            'archive_bytes':remote.size,'downloaded_bytes_this_run':remote.downloaded,
                            'speaker_selection':'Accent round-robin, lexicographic IDs; within-accent split alternation; 6 consecutive utterances >=25 using mic1.',
                            'clips':clips,'held_out_status':'sealed_until_configuration_freeze'})
        print('Saved '+str(manifest),flush=True)

def prefetch():
    """Download independent selected archive blocks with four bounded workers."""
    remote=RemoteZip(URL,ROOT/'.cache/vctk/ranges')
    with zipfile.ZipFile(remote) as archive:
        names=archive.namelist();info=archive.read(next(n for n in names if n.endswith('speaker-info.txt'))).decode()
        available={re.search(r'(p\d+)_',n).group(1) for n in names if n.endswith('_mic1.flac') and re.search(r'(p\d+)_',n) and '__MACOSX' not in n}
        splits=select_speakers(info,available);wanted=[]
        for speakers in splits.values():
            for speaker,_ in speakers:
                candidates=sorted(n for n in names if re.search(r'/'+speaker+r'/'+speaker+r'_\d+_mic1\.flac$',n)
                                  and int(re.search(r'_(\d+)_mic1',n).group(1))>=25)[:8]
                for name in candidates:
                    wanted.append(archive.getinfo(name));identity=Path(name).stem.removesuffix('_mic1')
                    wanted.extend(archive.getinfo(n) for n in names if n.endswith('/'+speaker+'/'+identity+'.txt'))
        blocks=set()
        for item in wanted:
            start=item.header_offset;end=start+30+len(item.filename.encode())+len(item.extra)+item.compress_size+65536
            blocks.update(range(start//remote.blocksize,end//remote.blocksize+1))
        existing=sum(p.stat().st_size for p in remote.cache.iterdir() if p.name.isdigit())
        missing=[b for b in sorted(blocks) if not (remote.cache/str(b)).exists()]
        if existing+len(missing)*remote.blocksize>400*1024*1024:raise ValueError('Subset cache transfer cap exceeded')
        def get(block):
            start=block*remote.blocksize;end=min(start+remote.blocksize,remote.size)-1
            req=urllib.request.Request(URL,headers={'Range':'bytes=%d-%d'%(start,end),'If-Range':remote.etag})
            with urllib.request.urlopen(req,timeout=90) as response:
                if response.status!=206:raise ValueError('Server ignored Range')
                data=response.read(remote.blocksize+1)
            if len(data)!=end-start+1:raise ValueError('Incomplete archive block')
            target=remote.cache/str(block);temp=target.with_suffix('.prefetch');temp.write_bytes(data);temp.replace(target)
            return block
        print('Prefetching %d independent archive blocks'%len(missing),flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i,_ in enumerate(pool.map(get,missing),1):
                if i%10==0:print('Prefetched %d/%d'%(i,len(missing)),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['fetch','prefetch']);args=parser.parse_args()
    fetch() if args.command=='fetch' else prefetch()
