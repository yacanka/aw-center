"""Assemble approved takes on the recorded presentation clock, then validate the export."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess as sp
import textwrap
import wave
from edit import edit, voice_set, select_filter
from sequence import position

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/aw-center-video'
WORK = OUT / '.work'
HERE = Path(__file__).resolve().parent
TITLE = 'AW_Center_Tanitim_TR'
MODULES = {
    'home':'Çalışma alanı', 'login':'Oturum ve hesap erişimi', 'compdocs':'Uygunluk belgeleri',
    'jira':'JIRA', 'translator':'Çeviri', 'jobs':'İş geçmişi', 'compare':'Belge karşılaştırma',
    'pdf':'PDF araçları', 'media-converter':'Medya dönüştürücü', 'integrations':'Entegrasyon kataloğu',
    'accelerator':'İş akışları', 'pptxGallery':'Sunum galerisi', 'ddfAssistant':'Doküman yorumları',
    'doors':'DOORS', 'teamcenter':'Teamcenter', 'developer':'Geliştirici araçları', 'users':'Kullanıcı yönetimi',
    'settings':'Hesap ayarları', 'organization':'Organizasyon'
}
def scene_context(scene):
    route=scene['route'].split('/')[2]
    module=MODULES[route]
    role=scene.get('displayRole') or {'manager':'Yönetici','editor':'Düzenleyici','viewer':'Görüntüleyici','public':'Oturum açmamış kullanıcı'}[scene.get('role','manager')]
    initial=f"{role}. {scene['route']} ekranı açıldı. {scene['title']} için örnek veriler hazır."
    return module,role,initial
def beat_role(scene,index,default):
    transitions={
        ('login',2):'Oturum açmamış kullanıcı → Yönetici', ('login',3):'Yönetici',
        ('invites',2):'Yönetici → Davetli', ('invites',3):'Davetli',
        ('public-recovery',3):'Oturum açmamış kullanıcı → Hesap sahibi',
        ('compliance-conflict',1):'İki yetkili kullanıcı'
    }
    return transitions.get((scene,index),default)
def run(cmd, **kw):
    return sp.run([str(v) for v in cmd],check=True,**kw)
def probe(file):
    return json.loads(sp.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(file)]))
def matches_frames(file,frames):
    try:
        return file.is_file() and int(probe(file)['streams'][0]['nb_frames'])==frames
    except (sp.CalledProcessError,KeyError,IndexError,ValueError):
        return False
def clock(seconds,sep='.'):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}{sep}{ms%1000:03}'
def assclock(s):
    return clock(s)[:-1].lstrip('0',) if s>=36000 else clock(s)[1:-1]
def escape(s):
    return s.replace('\\','').replace('{','(').replace('}',')').replace('\n',r'\N')
def caption(text, width=82):
    lines=textwrap.wrap(text,width=width,break_long_words=False,break_on_hyphens=False)
    if len(lines)>2:
        lines=textwrap.wrap(text,width=math.ceil(len(text)/2)+8,break_long_words=False,break_on_hyphens=False)
    if len(lines)>2: raise ValueError(f'Caption needs a shorter beat: {text}')
    return '\n'.join(lines)
ASS='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,34,&H00F6FAFA,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Title,Arial,23,&H00EBEFEE,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Label,Arial,17,&H00BBE6AD,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def entry(start,end,style,x,y,text):
    return f'Dialogue: 0,{assclock(start)},{assclock(end)},{style},,0,0,0,,{{\\pos({x},{y})}}{escape(text)}\n'
def place_audio(wavfile,scene,take):
    frames=take['stats']['frames']*1600
    position=0
    with wave.open(str(wavfile),'wb') as dest:
        dest.setparams((1,2,48000,0,'NONE','not compressed'))
        for clip in (c for beat in take['beats'] for c in beat['clips']):
            offset=round(clip['start']*48000)
            if offset<position: raise ValueError('Voice clips overlap')
            dest.writeframes(b'\0\0'*(offset-position))
            with wave.open(clip['wav'],'rb') as src:
                if src.getparams()[:3] != (1,2,48000):raise ValueError('Unexpected WAV')
                dest.writeframes(src.readframes(src.getnframes()))
                position=offset+src.getnframes()
        if position>frames: raise ValueError('Truncated voice')
        dest.writeframes(b'\0\0'*(frames-position))

def encode_scene(scene,take,number,pilot=False):
    folder=WORK/'takes'/scene['id']
    source=folder/take['stats'].get('file','take.mp4')
    if pilot:
        folder=folder/'pilot-cut'
        folder.mkdir(exist_ok=True)
    seconds=take['stats']['frames']/30
    ass=ASS+entry(0,seconds,'Label',44,992,'Temsili sonuç' if scene.get('simulated') else 'AW CENTER')
    ass+=entry(0,seconds,'Title',44,1037,caption(scene['title'],32))
    for clip in (c for beat in take['beats'] for c in beat['clips']):
        ass+=entry(clip['start'],clip['start']+clip['duration'],'Caption',530,1023,caption(clip['text']))
    subs=folder/'captions.ass'
    local=folder/'section.mp4'
    audio_hash=hashlib.sha256()
    for beat in take['beats']:
        for clip in beat['clips']:audio_hash.update(Path(clip['wav']).read_bytes())
    fingerprint=hashlib.sha256((ass+audio_hash.hexdigest()+str(source.stat().st_mtime_ns)+'limited-range-captions-v3'+str(take['intervals'])).encode()).hexdigest()
    stamp=folder/'render-key'
    if stamp.exists() and matches_frames(local,take['stats']['frames']):
        if stamp.read_text()==fingerprint:return local
        # A section made during assembly can be reused if its exact PCM, subtitles
        # and source edit list also match the published encoding key.
        prior=hashlib.sha256((ass+str(source.stat().st_mtime_ns)+'limited-range-captions-v3'+str(take['intervals'])).encode()).hexdigest()
        if stamp.read_text()==prior and (folder/'mix.wav').exists():
            reference=folder/'verify-mix.wav'
            place_audio(reference,scene,take)
            same=reference.read_bytes()==(folder/'mix.wav').read_bytes()
            reference.unlink()
            if same:
                stamp.write_text(fingerprint)
                return local
    subs.write_text(ass)
    audio=folder/'mix.wav'
    place_audio(audio,scene,take)
    video_filter="fps=30,tpad=stop_mode=clone:stop_duration=0.1,"+select_filter(take['intervals'])+f"tpad=stop_mode=clone:stop={take['stats']['frames']},trim=end_frame={take['stats']['frames']},"+'scale=in_range=full:out_range=limited:out_color_matrix=bt709,format=yuv420p,pad=1920:1080:0:0:color=0x152D32,drawbox=x=0:y=968:w=1920:h=3:c=0x72B6A5:t=fill,drawbox=x=496:y=987:w=2:h=73:c=0x48615F:t=fill,ass=captions.ass'
    pending=folder/f'section.{os.getpid()}.next.mp4'
    try:
        run(['ffmpeg','-y','-loglevel','error','-threads','2','-i',source,'-i',audio,'-vf',video_filter,'-c:v','libx264','-threads','3','-crf','18','-preset','veryfast','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709','-c:a','alac','-movflags','+faststart',pending],cwd=folder)
        if not matches_frames(pending,take['stats']['frames']):raise ValueError(f'Section frame count failed: {scene["id"]}')
        pending.replace(local)
    finally:
        pending.unlink(missing_ok=True)
    stamp.write_text(fingerprint)
    return local

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--sections-only',action='store_true')
    parser.add_argument('--only',nargs='+')
    parser.add_argument('--available',action='store_true',help='Export recorded scenes only and list open gaps')
    args=parser.parse_args()
    scenes=json.loads(sp.check_output(['node',HERE/'record.mjs','list']))
    if args.pilot:scenes=[s for s in scenes if s['id']=='pilot']
    if args.only:scenes=[s for s in scenes if s['id'] in args.only]
    scenes.sort(key=position)
    missing=[s for s in scenes if not (WORK/'takes'/s['id']/'take.json').exists()]
    if missing and not args.available and not args.sections_only:raise SystemExit('Missing recordings: '+', '.join(s['id'] for s in missing))
    rendered=[]; manifest=[]; chapters=[]; captions=[]; narration=[]; rows=[]; cursor=0
    import sys
    sys.path.insert(0,str(HERE/'audio'))
    from synthesize import pronunciations
    voice_set([s for s in scenes if s not in missing])
    for index,scene in enumerate(scenes,1):
        folder=WORK/'takes'/scene['id']
        if scene in missing:
            for i,beat in enumerate(scene['beats'],1):
                rows.append([f"{scene['id']}.{i}",scene['title'],scene.get('role','manager'),scene['route'],beat.get('feature',beat['text']), 'Senaryo tanımlı',beat['text'],beat.get('expected',''), 'Yerel demo', '', scene['id'],'','Çekim doğrulanmadı'])
            continue
        take=json.loads((folder/'take.json').read_text())
        source=folder/take['stats'].get('file','take.mp4')
        raw=probe(source)['streams'][0]
        if (raw['width'],raw['height'])!=(1920,968):raise ValueError('Invalid capture')
        raw_stats=take['stats'].copy()
        take=edit(scene,take,source,args.pilot)
        rendered.append(encode_scene(scene,take,index,args.pilot))
        print('Montaj',scene['id'],f"{take['stats']['duration']:.1f}s",flush=True)
        length=take['stats']['frames']/30
        module,role,initial=scene_context(scene)
        condition=initial
        chapters.append(f"{clock(cursor)[:-4]}  {scene['title']}")
        details=[]
        narration.append(scene['title']+'\n')
        for i,(beat,tm) in enumerate(zip(scene['beats'],take['beats'],strict=True),1):
            begin=cursor+tm['voiceStart'];end=begin+tm['voiceDuration']
            for clip in tm['clips']:
                captions.append(f'{len(captions)+1}\n{clock(cursor+clip["start"],",")} --> {clock(cursor+clip["start"]+clip["duration"],",")}\n{caption(clip["text"])}\n')
                clip['wav']=os.path.relpath(clip['wav'],OUT)
            narration.extend(c['text'] for c in tm['clips'])
            steps=[e['kind'] for e in tm['events'] if e['kind']!='sonuç_görünüyor']
            result=beat.get('expected') or beat.get('feature') or scene['title']
            label=beat.get('feature') or scene['title']
            stamps=clock(cursor+tm['start'])+' – '+clock(cursor+tm['end'])
            rows.append([f"{scene['id']}.{i}",module,beat_role(scene['id'],i,role),tm['actualRoute'],label,condition,beat['text']+' ('+', '.join(dict.fromkeys(steps or ['Sonuç beklenir']))+')',result,'İzole Django / SQLite','Temsili sonuç' if scene.get('simulated') else 'Gerçek arayüz ve demo kayıtları',scene['id'],stamps,'Kaydedildi'])
            condition=result
            for event in tm['events']:
                event['sourceSeconds']=round(max(tm['source']['start'],min(tm['source']['end'],event['seconds']-take['eventClockOffset'])),3)
                source_frame=round(event['sourceSeconds']*30)
                elapsed=0
                for a,b in take['intervals']:
                    if a=='hold':elapsed+=b;continue
                    if source_frame<a:break
                    elapsed+=min(b,source_frame)-a
                    if source_frame<b:break
                event['finalSeconds']=round(cursor+max(tm['start'],min(tm['end'],elapsed/30)),3)
            if not any(e['kind']=='sonuç_görünüyor' for e in tm['events']):
                tm['events'].append({'kind':'sonuç_görünüyor','sourceSeconds':tm['source']['ready'],'finalSeconds':round(cursor+tm['ready'],3)})
            details.append({**beat,'wav':os.path.relpath(beat['wav'],OUT),'spoken':pronunciations(beat.get('spoken') or beat['text']),'timing':tm,'finalStart':begin,'finalEnd':end,'finalActionStart':cursor+tm['start'],'finalActionEnd':cursor+tm['end']})
        narration.append('')
        manifest.append({**scene,'module':module,'role':scene.get('role','manager'),'fixture':'Atlas demo / 08.11.2026','start':cursor,'end':cursor+length,'initialState':initial,'take':os.path.relpath(source,OUT),'cutsAt30Fps':take['intervals'],'capture':raw_stats,'beats':details})
        cursor+=length
    if args.sections_only:return
    if not args.pilot:
        for path in [HERE/'business/gaps.json',HERE/'audio/admin-gaps.json',HERE/'gaps.json']:
            if not path.is_file():continue
            for gap in json.loads(path.read_text()):
                route_key=gap['route'].removeprefix('/app/').split('/')[0]
                rows.append([f'K-{len(rows)+1}', MODULES.get(route_key,'Uygulama kabuğu'), gap.get('role','Yetkili kullanıcı'), gap['route'],gap['feature'],'', '',gap['reason'],'Kaynak ve arayüz incelemesi','','','','Açık kapsam'])
    target=WORK/'pilot' if args.pilot else OUT
    target.mkdir(exist_ok=True)
    write=lambda name,data:(target/name).write_text(data,encoding='utf-8')
    write('chapters.txt','\n'.join(chapters)+'\n')
    write(TITLE+'.srt','\n'.join(captions)+'\n')
    write('narration_tr.txt','\n'.join(narration).strip()+'\n')
    write('scenes.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with (target/'feature-coverage.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.writer(handle)
        writer.writerow(['Özellik kimliği','Modül','Rol','Route/ekran','Pencere veya alt akış','Başlangıç koşulu','Kullanıcı işlemi','Beklenen sonuç','Veri kaynağı','Gerçek/simüle edilen bölüm','Sahne kimliği','Nihai zaman damgası','Durum'])
        writer.writerows(rows)
    concat=target/'.concat.txt' if args.pilot else WORK/'concat.txt'
    concat.write_text(''.join("file '"+str(p).replace("'","'\\''")+"'\n" for p in rendered))
    cmd=['ffmpeg','-nostdin','-hide_banner','-f','concat','-safe','0','-i',concat]
    analysis=run(cmd+['-vn','-af','loudnorm=I=-16:LRA=8:TP=-1.5:print_format=json','-f','null','-'],capture_output=True,text=True)
    level=json.loads(re.findall(r'\{[^{}]*"input_i"[^{}]*\}',analysis.stderr)[-1])
    loud='loudnorm=I=-16:LRA=8:TP=-1.5:linear=true'+''.join(f':{key}={level[src]}' for key,src in [('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')])
    # AAC reconstruction can overshoot a PCM peak. Limit short peaks before
    # encoding, with lookahead compensation so the cues retain their timestamps.
    loud+=',aresample=192000,alimiter=limit=0.74:attack=2:release=60:level=0:latency=1,aresample=48000'
    dest=target/('pilot.mp4' if args.pilot else TITLE+'.mp4')
    temp=dest.with_suffix('.next.mp4')
    metadata=target/'.chapters.ffmeta' if args.pilot else WORK/'chapters.ffmeta'
    metadata.write_text(';FFMETADATA1\n'+''.join(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(s['start']*1000)}\nEND={round(s['end']*1000)}\ntitle={s['title']}\n" for s in manifest))
    run(cmd+['-loglevel','error','-y','-f','ffmetadata','-i',metadata,'-map','0:v:0','-map','0:a:0','-map_chapters','1','-metadata','title=AW Center Tanıtımı','-metadata:s:a:0','language=tur','-c:v','copy','-af',loud,'-c:a','aac','-ar','48000','-b:a','160k','-movflags','+faststart',temp])
    info=probe(temp)
    video=next(x for x in info['streams'] if x['codec_type']=='video')
    audio=next(x for x in info['streams'] if x['codec_type']=='audio')
    assert (video['width'],video['height'],video['codec_name'],video['pix_fmt'],video['r_frame_rate'],audio['codec_name'])==(1920,1080,'h264','yuv420p','30/1','aac')
    assert abs(float(video['duration'])-float(audio['duration']))<.1
    assert abs(cursor-float(video['duration']))<.1
    run(['ffmpeg','-nostdin','-v','error','-xerror','-threads','3','-i',temp,'-f','null','-'])
    temp.replace(dest)
    (WORK/('pilot-technical.json' if args.pilot else 'technical.json')).write_text(json.dumps(info,indent=2))
    print(dest,clock(cursor),len(rendered),'scenes')
if __name__=='__main__':main()
