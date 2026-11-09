"""Remove measured visual waits while keeping UI transitions and verified results."""
import hashlib
import json
import math
import re
import subprocess as sp
import sys
import wave
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'audio'))
from synthesize import render as speak, pronunciations
WORK=HERE.parents[1]/'artifacts/aw-center-video/.work'

def wav_seconds(file):
    with wave.open(str(file),'rb') as f:return f.getnframes()/f.getframerate()

def segments(beat):
    text=beat['text']
    parts=re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])',text)
    # Keep decimal numbers, quoted phrases and product names intact.
    if len(parts)!=2 or beat.get('spoken') or any(len(p)<20 for p in parts):
        return [(text,beat['wav'])]
    return [(p,str(WORK/'speech'/(hashlib.sha256(p.encode()).hexdigest()[:16]+'.wav'))) for p in parts]

def bridges():
    data={}
    for f in [HERE/'bridges.json',HERE/'business/bridges.json',HERE/'audio/bridges.json']:
        if f.is_file():data.update(json.loads(f.read_text()))
    return data

def bridge_clips(scene_id,i,lines):
    text=lines.get(f'{scene_id}.{i}','')
    if not text:return []
    return [(s,str(WORK/'speech'/(hashlib.sha256(s.encode()).hexdigest()[:16]+'.wav')))
            for s in re.split(r'(?<=[.!?])\s+',text.strip()) if s]

def voice_set(scenes):
    requests={}; lines=bridges()
    for scene in scenes:
        for i,beat in enumerate(scene['beats']):
            for text,file in segments(beat)+bridge_clips(scene['id'],i,lines):
                requests[file]={'output':file,'text':text}
                if text==beat['text'] and beat.get('spoken'):requests[file]['pronunciation']=beat['spoken']
    if requests:speak(list(requests.values()))

def frame_activity(source):
    cache=source.with_suffix('.motion.json')
    if cache.exists() and cache.stat().st_mtime_ns>=source.stat().st_mtime_ns:
        return json.loads(cache.read_text())
    proc=sp.Popen(['ffmpeg','-v','error','-threads','1','-i',str(source),'-vf','fps=5,scale=384:194,format=gray','-filter_threads','1','-threads','1','-f','rawvideo','pipe:1'],stdout=sp.PIPE)
    prev=None;active=[]
    while raw:=proc.stdout.read(384*194):
        frame=np.frombuffer(raw,dtype=np.uint8).astype(np.int16)
        if len(frame)!=384*194:raise ValueError('Truncated frame')
        active.append(prev is None or bool(np.count_nonzero(abs(frame-prev)>8)>=5))
        prev=frame
    if proc.wait():raise RuntimeError('Motion sampling failed')
    cache.write_text(json.dumps(active))
    return active

def compress_waits(start,end,activity):
    # A 5 Hz motion scan retains a generous margin on both sides of moving pixels.
    # Keep the first and last 0.4 seconds of each stationary interval for reading.
    if end<=start:return []
    spans=[];quiet=None
    def finish_quiet(a,b):
        if b-a>46:spans.append((a+14,b-12))
    for frame in range(start,end):
        idx=frame//6
        moving=any(activity[max(0,idx-1):idx+3])
        if not moving and quiet is None:quiet=frame
        if moving and quiet is not None:finish_quiet(quiet,frame);quiet=None
    if quiet is not None:finish_quiet(quiet,end)
    intervals=[];pos=start
    for a,b in spans:
        if a>pos:intervals.append((pos,a))
        pos=b
    if pos<end:intervals.append((pos,end))
    return intervals

def edit(scene,take,source,pilot=False):
    activity=frame_activity(source)
    bridge_lines=bridges()
    measured=[];source_intervals=[];total=0
    source_frames=take['stats']['frames']
    previous_source_end=0
    def add(a,b):
        nonlocal total
        if b<=a:return
        if source_intervals and source_intervals[-1][1]==a:source_intervals[-1][1]=b
        else:source_intervals.append([a,b])
        total+=b-a
    for i,(beat,old) in enumerate(zip(scene['beats'],take['beats'],strict=True)):
        begin=total
        # Drop recorder setup and screenshot bookkeeping between independent actions.
        raw_start=max(0,min(source_frames-1,round(old['start']*30))-3)
        raw_start=max(raw_start,previous_source_end)
        raw_ready=min(source_frames,math.ceil(old['ready']*30))
        raw_end=min(source_frames,round(old['end']*30))
        actions=compress_waits(raw_start,raw_ready,activity)
        if pilot and take['stats']['duration']>30:
            # A short pilot retains the gestures, the first progress view and the
            # terminal result. Keep source frames on both sides of every choice.
            marks=[round((event['seconds']-take['eventClockOffset'])*30) for event in old['events']
                   if event['kind'] in ('dosya_seçildi','tıklandı','dosya_indirildi')]
            windows=sorted([(raw_start,raw_start+12),(raw_ready-27,raw_ready)]
                           +[(m-42,m+22) for m in marks])
            actions=[]
            for a,b in windows:
                a,b=max(raw_start,a),min(raw_ready,b)
                if b<=a:continue
                if actions and a<=actions[-1][1]:actions[-1]=(actions[-1][0],max(actions[-1][1],b))
                else:actions.append((a,b))
        for a,b in actions:add(a,b)
        ready=total
        clips=[]
        pieces=segments(beat)
        for text,file in pieces:
            clips.append({'text':text,'spoken':pronunciations(beat.get('spoken') or text),'wav':file,'duration':wav_seconds(file)})
        first=clips[0]
        # Reports of a completed result start on the verified view. Instructions can
        # begin over a gesture. In a two-sentence explanation the result is its own WAV.
        verb=re.search(r'(yoruz|alım|elim|seçip|girip|açıp|için |istediğimiz|yazınca)',first['text'],re.I)
        result_only=re.match(r'(İş tamam|Tamamlan|Onaydan sonra|Sonuçta|İndiri|Sonuç kodu)',first['text'])
        if (verb or beat.get('during') or len(clips)==2) and not result_only:
            first_at=begin+.1*30
            if len(clips)==1 and not beat.get('during'):
                first_at=max(first_at,ready-first['duration']*30*.7)
        else:first_at=ready
        first['start']=first_at/30
        if len(clips)==2:
            clips[1]['start']=max(ready/30,first['start']+first['duration']+.16)
        # Additional action narration belongs only inside a real, measured pause.
        # Leave room for both the preceding sentence and the verified outcome.
        openings=[(max(begin/30,clips[j-1]['start']+clips[j-1]['duration']) if j else begin/30,c['start']) for j,c in enumerate(clips)]
        # Instructions can finish while the operator is still filling a form.
        # The next observed result bounds narration for that remaining action.
        openings.append((clips[-1]['start']+clips[-1]['duration'],ready/30))
        left,right=max(openings,key=lambda gap:gap[1]-gap[0])
        candidates=bridge_clips(scene['id'],i,bridge_lines)
        if candidates and right-left>5 and not pilot:
            extras=[]
            for text,file in candidates:
                length=wav_seconds(file)
                if length+sum(e['duration']+.16 for e in extras)>right-left-.34:break
                extras.append({'text':text,'spoken':pronunciations(text),'wav':file,'duration':length})
            raw_pause=(right-left-sum(e['duration']+.16 for e in extras))/2
            spread=raw_pause>7 and len(extras)>1
            between=(right-left-sum(e['duration'] for e in extras))/(len(extras)+1) if spread else .16
            pos=left+(between if spread else raw_pause)
            for c in extras:
                c['start']=pos
                pos+=c['duration']+between
                clips.append(c)
            clips.sort(key=lambda c:c['start'])
        speech_end=clips[-1]['start']+clips[-1]['duration']
        want=max(13,math.ceil((speech_end+.28)*30)-ready)
        remaining=max(0,raw_end-raw_ready)
        add(raw_ready,raw_ready+min(want,remaining))
        previous_source_end=raw_ready+min(want,remaining)
        if want>remaining:
            # A short held result tail is legitimate only on the verified view.
            source_intervals.append(['hold',want-remaining])
            total+=want-remaining
        measured.append({**old,'source':dict(start=old['start'],ready=old['ready'],end=old['end']),'start':begin/30,'ready':ready/30,'voiceStart':clips[0]['start'],'voiceDuration':speech_end-clips[0]['start'],'end':total/30,'clips':clips})
    return {**take,'stats':{**take['stats'],'frames':total,'duration':total/30},'beats':measured,'intervals':source_intervals}

def select_filter(intervals):
    source=[];holds=[];frames=0
    for a,b in intervals:
        if a=='hold':holds.append(f'gte(N,{frames})*{b}')
        else:
            source.append(f'between(n,{a},{b-1})')
            frames+=b-a
    pts='N'+('+'+'+'.join(holds) if holds else '')
    return "select='"+'+'.join(source)+"',setpts='("+pts+")/(30*TB)',fps=30:start_time=0,"
