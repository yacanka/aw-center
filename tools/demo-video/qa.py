"""Check the final media, download contents and every published time interval."""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess as sp
import tempfile
from io import BytesIO
from pathlib import Path
from docx import Document
from PIL import Image, ImageDraw, ImageFont
from render import OUT, WORK, TITLE, probe, clock, caption
from backend_demo.verify_downloads import DEMO_STATE, decode, package_contents, private_output_check, private_value_detector

def verify_downloads(scenes):
    files=[]
    for scene in scenes:
        for beat in scene['beats']:
            for event in beat['timing']['events']:
                if event['kind']!='dosya_indirildi':continue
                path=WORK/'downloads'/scene['id']/event['file']
                data=path.read_bytes()
                detail=decode(path.name,data)
                if scene['id']=='pilot':
                    assert Document(BytesIO(data)).paragraphs[0].text=='Atlas document management plan'
                if scene['id']=='outlook':
                    reference=(DEMO_STATE/'examples/atlas.docx').read_bytes()
                    assert package_contents(data)==package_contents(reference), 'Outlook attachment differs from its fixture'
                if scene['id']=='media':
                    assert detail['width']==640
                files.append({'scene':scene['id'],'file':event['file'],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'format':detail['format']})
    return files

def check_timestamps(scenes,length):
    previous=0
    for scene in scenes:
        assert abs(scene['start']-previous)<.002
        previous=scene['end']
        for beat in scene['beats']:
            assert scene['start']<=beat['finalActionStart']<=beat['finalStart']<beat['finalEnd']<=scene['end']+.01
            assert beat['finalEnd']<=beat['finalActionEnd']+.01<=scene['end']+.02
    assert abs(previous-length)<.12
    srt=(OUT/(TITLE+'.srt')).read_text().strip().split('\n\n')
    flat=[b for scene in scenes for b in scene['beats']]
    clips=[(s['start'],c) for s in scenes for b in s['beats'] for c in b['timing']['clips']]
    assert len(srt)==len(clips)
    for number,(block,(offset,c)) in enumerate(zip(srt,clips,strict=True),1):
        lines=block.splitlines()
        assert 3<=len(lines)<=4 and lines[0]==str(number)
        assert lines[1]==clock(offset+c['start'],',')+' --> '+clock(offset+c['start']+c['duration'],',')
        assert lines[2:]==caption(c['text']).splitlines()
    expected=[text for scene in scenes for text in [scene['title'],*(clip['text'] for beat in scene['beats'] for clip in beat['timing']['clips'])]]
    assert (OUT/'narration_tr.txt').read_text().split()==' '.join(expected).split()
    chapter_lines=(OUT/'chapters.txt').read_text().splitlines()
    assert chapter_lines==[f"{clock(scene['start'])[:-4]}  {scene['title']}" for scene in scenes]
    with (OUT/'feature-coverage.csv').open(encoding='utf-8-sig') as f:
        rows=list(csv.reader(f))[1:]
    shown=[r for r in rows if r[-1]=='Kaydedildi']
    assert len(shown)==len(flat)
    for row,beat in zip(shown,flat,strict=True):
        assert row[-2]==clock(beat['finalActionStart'])+' – '+clock(beat['finalActionEnd'])
    chapters=json.loads(sp.check_output(['ffprobe','-v','error','-show_chapters','-of','json',str(OUT/(TITLE+'.mp4'))]))['chapters']
    assert len(chapters)==len(scenes)
    for marker,scene in zip(chapters,scenes,strict=True):
        assert marker['tags']['title']==scene['title'] and abs(float(marker['start_time'])-scene['start'])<.002
    return len(flat)

def caption_widths(scenes):
    font_root=Path('/System/Library/Fonts/Supplemental')
    regular,bold=font_root/'Arial.ttf',font_root/'Arial Bold.ttf'
    if not all(path.is_file() for path in (regular,bold)):return None
    regular=ImageFont.truetype(str(regular),34)
    bold=ImageFont.truetype(str(bold),23)
    captions=(OUT/(TITLE+'.srt')).read_text().strip().split('\n\n')
    speech=max(regular.getlength(line) for block in captions for line in block.splitlines()[2:])
    titles=max(bold.getlength(line) for scene in scenes for line in caption(scene['title'],32).splitlines())
    assert speech<=1390 and titles<=448
    return {'subtitle':round(speech),'title':round(titles)}

def sample_frames(movie,scenes,white_candidates=(),digest=None):
    # Pictures come from the final MP4. Each row covers a chapter start and verified outcomes.
    qa=WORK/'visual-qa'
    qa.mkdir(exist_ok=True)
    digest=digest or sha256_file(movie)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',16) if Path('/System/Library/Fonts/Supplemental/Arial.ttf').exists() else ImageFont.truetype('DejaVuSans.ttf',16)
    marks=[]
    for scene in scenes:
        marks.append((scene['start']+.2,scene['id']+' · giriş'))
        for index,beat in enumerate(scene['beats'],1):
            when=max(beat['finalStart'],scene['start']+beat['timing']['ready'])+.21
            when=min(when,scene['end']-.1)
            marks.append((when,f"{scene['id']} · {index}"))
    for candidate in white_candidates:
        marks.append((candidate['start']+candidate['duration']/2,'Beyaz alan tarama adayı'))
    sheets=[]
    for n in range(0,len(marks),12):
        batch=marks[n:n+12]
        dest=qa/f'{n//12+1:02}.jpg'
        stamp=dest.with_suffix('.inputs.json')
        marker_key=json.dumps(['visual-qa-v2',digest,[(f'{sec:.3f}',label) for sec,label in batch]],ensure_ascii=False)
        key=hashlib.sha256(marker_key.encode()).hexdigest()
        try:
            meta=json.loads(stamp.read_text())
            if meta.get('inputs')==key and dest.is_file() and meta.get('jpeg')==sha256_file(dest):
                sheets.append(dest.name)
                continue
        except (OSError,ValueError):
            pass
        sheet=Image.new('RGB',(3*460,4*285),'#e7eeee')
        draw=ImageDraw.Draw(sheet)
        for i,(sec,label) in enumerate(batch):
            cmd=['ffmpeg','-nostdin','-loglevel','error','-ss',f'{sec:.3f}','-threads','1','-i',str(movie),'-frames:v','1','-vf','scale=460:258','-threads','1','-f','image2pipe','-c:v','mjpeg','pipe:1']
            pic=Image.open(BytesIO(sp.check_output(cmd)))
            x=(i%3)*460;y=(i//3)*285
            sheet.paste(pic,(x,y));draw.text((x+7,y+260),clock(sec)[:-4]+'   '+label,font=font,fill='#233638')
        with tempfile.NamedTemporaryFile(dir=qa,suffix='.tmp',delete=False) as binary:
            temp=Path(binary.name)
            sheet.save(binary,format='JPEG',quality=83)
        temp.replace(dest)
        with tempfile.NamedTemporaryFile(dir=qa,mode='w',suffix='.tmp',delete=False) as handle:
            manifest=Path(handle.name)
            json.dump({'inputs':key,'jpeg':sha256_file(dest),'video':digest},handle)
        manifest.replace(stamp)
        sheets.append(dest.name)
    return sheets,len(marks)

def screen_privacy(movie,scenes):
    executable=shutil.which('tesseract')
    if not executable:
        return {'available':False,'frames':0,'scenes':[]}
    tests={'login':[1],'invites':[0,1],'invitation-audit':[1],'member-password':[0],
           'jira-watcher':[0], 'reset-apply':[0,1],'public-recovery':[0],'reset':[0]}
    detect=private_value_detector()
    samples=[]
    for scene in scenes:
        for i in tests.get(scene['id'], []):
            if i>=len(scene['beats']):continue
            beat=scene['beats'][i]
            start=beat['finalActionStart']
            ready=scene['start']+beat['timing']['ready']
            for sec in sorted({(start+ready)/2, min(ready+.15,scene['end']-.1)}):
                image=sp.check_output(['ffmpeg','-nostdin','-v','error','-ss',f'{sec:.3f}','-threads','1','-i',str(movie),'-frames:v','1','-threads','1','-f','image2pipe','-c:v','png','pipe:1'])
                # Keep OCR text in memory: an unexpected credential must never enter a diagnostic.
                ocr=sp.run([executable,'stdin','stdout','--psm','11','-l','eng'],input=image,capture_output=True,check=True,env={**os.environ,'OMP_THREAD_LIMIT':'1'})
                text=ocr.stdout.decode(errors='replace')
                if len(text.strip())<12:raise ValueError(f'OCR produced no usable text at {clock(sec)}')
                if detect(text):raise ValueError(f'Possible credential on screen at {clock(sec)}')
                samples.append({'scene':scene['id'],'seconds':round(sec,3)})
    return {'available':True,'frames':len(samples),'scenes':sorted({s['scene'] for s in samples}),'samples':samples}

def measure_ranges(scenes,scan_log,white_log):
    def chapter(sec):
        return next((scene['title'] for scene in scenes if scene['start']<=sec<scene['end']),scenes[-1]['title'])
    talks=[(scene['start']+clip['start'],scene['start']+clip['start']+clip['duration'])
           for scene in scenes for beat in scene['beats'] for clip in beat['timing']['clips']]
    pauses=[]
    for end,seconds in re.findall(r'silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)',scan_log):
        end=float(end);seconds=float(seconds);begin=max(0,end-seconds)
        talk=sum(max(0,min(end,b)-max(begin,a)) for a,b in talks)
        pauses.append({'start':round(begin,3),'duration':seconds,'scene':chapter(begin),'duringCueSeconds':round(talk,2)})
    whites=[]
    for start,seconds in re.findall(r'black_start:([0-9.]+).*?black_duration:([0-9.]+)',white_log):
        whites.append({'start':float(start),'duration':float(seconds),'scene':chapter(float(start))})
    return pauses,whites

def sha256_file(file):
    with file.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def check_playback(scenes,playback):
    assert [row['id'] for row in playback]==[scene['id'] for scene in scenes]
    samples=0
    for scene,row in zip(scenes,playback,strict=True):
        assert [sample['kind'] for sample in row['samples']]==['giriş','etkileşim','sonuç']
        for sample in row['samples']:
            assert scene['start']-.05<=sample['before']<scene['end'] and sample['after']>sample['before']
            assert (sample['width'],sample['height'])==(1920,1080) and sample['ready']>=2
            samples+=1
    return samples

def visual_scan(video):
    packet_info=sp.check_output(['ffmpeg','-nostdin','-v','error','-i',str(video),'-map','0:v:0','-c:v','copy','-f','streamhash','-hash','sha256','-'],text=True)
    stream_digest=re.search(r'SHA256=([0-9a-fA-F]{64})',packet_info,re.I).group(1).lower()
    stream=sp.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_data_hash','sha256','-show_entries',
                            'stream=codec_name,extradata_hash,width,height,pix_fmt,color_range,start_time,duration,nb_frames,r_frame_rate,time_base','-of','json',str(video)],text=True)
    graph=('split=2[black][white];[white]crop=iw:968:0:0,fps=3,scale=320:162,negate,'
           'blackdetect@ui_white=d=0.7:pix_th=0.035:pic_th=0.999,nullsink;'
           '[black]scale=320:180,blackdetect@ui_black=d=0.3:pix_th=0.08')
    key=hashlib.sha256(json.dumps(['video-scan-v1',stream_digest,json.loads(stream),graph],sort_keys=True).encode()).hexdigest()
    cache=WORK/'visual-scan.json'
    try:
        saved=json.loads(cache.read_text())
        if saved['key']==key:return saved
    except (OSError,ValueError,KeyError):
        pass
    print('Scanning final H.264 picture stream:',stream_digest[:16],flush=True)
    capture=sp.run(['ffmpeg','-nostdin','-hide_banner','-nostats','-threads','3','-i',str(video),'-an','-filter_threads','1',
                    '-vf',graph,'-f','null','-'],capture_output=True,text=True,check=True)
    hits=[line for line in capture.stderr.splitlines() if 'black_start:' in line]
    black=[line for line in hits if 'blackdetect@ui_black' in line]
    white=[line for line in hits if 'blackdetect@ui_white' in line]
    saved={'key':key,'videoSha256':stream_digest,'black':black,'white':white}
    with tempfile.NamedTemporaryFile(dir=WORK,mode='w',suffix='.tmp',delete=False) as handle:
        temp=Path(handle.name)
        json.dump(saved,handle,indent=2)
    temp.replace(cache)
    return saved

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report-only',action='store_true',help='Regenerate the report from verified media and recorded observations.')
    parser.add_argument('--sheets-only',action='store_true',help='Prepare final MP4 contact sheets for visual inspection.')
    parser.add_argument('--visual-scan',action='store_true',help='Scan or reuse black and white interval measurements for the H.264 stream.')
    args=parser.parse_args()
    if args.report_only:
        result=json.loads((WORK/'qa.json').read_text())
        if result['sha256']!=sha256_file(OUT/(TITLE+'.mp4')):raise SystemExit('QA data belongs to a different video')
        write_report(result)
        private_output_check()
        return
    video=OUT/(TITLE+'.mp4')
    if args.visual_scan:
        scan=visual_scan(video)
        print('Verified H.264 stream',scan['videoSha256'],'; black intervals',len(scan['black']),'; near-white candidates',len(scan['white']))
        return
    scenes=json.loads((OUT/'scenes.json').read_text())
    digest=sha256_file(video)
    if args.sheets_only:
        sheets,marks=sample_frames(video,scenes,digest=digest)
        print('Final media frames:',marks,'; contact sheets:',len(sheets))
        return
    info=probe(video)
    length=float(info['format']['duration'])
    video_stream=next(stream for stream in info['streams'] if stream['codec_type']=='video')
    audio_stream=next(stream for stream in info['streams'] if stream['codec_type']=='audio')
    assert (video_stream['width'],video_stream['height'],video_stream['codec_name'],video_stream['pix_fmt'],video_stream['r_frame_rate'])==(1920,1080,'h264','yuv420p','30/1')
    assert (audio_stream['codec_name'],audio_stream['sample_rate'],audio_stream['channels'])==('aac','48000',1)
    assert abs(float(video_stream['duration'])-float(audio_stream['duration']))<.1
    count=check_timestamps(scenes,length)
    downloads=verify_downloads(scenes)
    proc=sp.run(['ffmpeg','-nostdin','-hide_banner','-nostats','-i',str(video),'-vn','-af','silencedetect=n=-55dB:d=4,loudnorm=I=-16:TP=-1.5:LRA=8:print_format=json','-f','null','-'],capture_output=True,check=True,text=True)
    loud=json.loads(re.findall(r'\{[^{}]*"input_i"[^{}]*\}',proc.stderr)[-1])
    if abs(float(loud['input_i'])+16)>1.5 or float(loud['input_tp'])> -1.5:
        raise ValueError(f"Final AAC level outside target ({loud['input_i']} LUFS, {loud['input_tp']} dBTP)")
    scan=visual_scan(video)
    pauses,white=measure_ranges(scenes,proc.stderr,'\n'.join(scan['white']))
    black=re.findall('black_duration:([0-9.]+)','\n'.join(scan['black']))
    assert not black,black
    sheets,marks=sample_frames(video,scenes,white,digest)
    ocr=screen_privacy(video,scenes)
    private_files=private_output_check()
    playback=json.loads((WORK/'playback.json').read_text())
    plays=check_playback(scenes,playback)
    result={'seconds':length,'bytes':video.stat().st_size,'chapters':len(scenes),'beats':count,'lufs':loud['input_i'],'truePeak':loud['input_tp'],'downloads':downloads,'blackIntervals':black,'pictureSha256':scan['videoSha256'],'blankWhiteCandidates':white,'pausesOver4s':pauses,'screenPrivacy':ocr,'privateTextFiles':private_files,'captionWidths':caption_widths(scenes),'sha256':digest,'playbackChapters':len(playback),'playbackSamples':plays,'sampledFrames':marks,'sheets':sheets}
    (WORK/'qa.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    write_report(result)
    final_file_count=private_output_check()
    if final_file_count!=result['privateTextFiles']:
        result['privateTextFiles']=final_file_count
        (WORK/'qa.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
        write_report(result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['downloads','sheets','pausesOver4s','screenPrivacy']},ensure_ascii=False))
def write_report(result):
    with (OUT/'feature-coverage.csv').open(encoding='utf-8-sig') as f:
        rows=list(csv.reader(f))[1:]
    gaps=[r for r in rows if r[-1]!='Kaydedildi']
    srt_count=len((OUT/(TITLE+'.srt')).read_text().strip().split('\n\n'))
    digest=result['sha256']
    pauses=result['pausesOver4s']
    if pauses:
        longest=max(pauses,key=lambda item:item['duration'])
        between=sum(p['duringCueSeconds']<=.3 for p in pauses)
        pause_note=(f"−55 dB altında en az 4 saniye süren {len(pauses)} aralık ölçüldü. "
                    f"En uzunu {longest['duration']:.1f} saniye, {clock(longest['start'])} konumunda “{longest['scene']}” bölümünde. "
                    f"{between} aralık, 0,3 saniye toleransla zamanlanmış anlatım parçalarının arasına düşüyor.")
    else:
        pause_note="−55 dB altında en az 4 saniye süren sessizlik ölçülmedi. Daha kısa duraklamaların en uzun süresi bu eşikle ölçülmez."
    whites=result['blankWhiteCandidates']
    white_note=(f"Uygulamanın üst 968 piksellik alanı saniyede üç örnekle tarandı. Beyaza yakın piksellerin alanın en az %99,9’unu kapladığı "
                f"{len(whites)} aralık algılandı. FFmpeg süre eşiği 0,7 saniye, örnekleme adımı saniyenin üçte biri. Bu çözünürlükte bir aday 0,67 saniye olarak da raporlanabilir." if whites else "Uygulamanın üst 968 piksellik alanındaki beyaza yakın bölgeler saniyede üç örnekle tarandı. %99,9 alan ve 0,7 saniye eşikleriyle aralık saptanmadı.")
    white_ranges=[f"- {clock(w['start'])} · {w['duration']:.2f} saniye · {w['scene']}" for w in whites]
    if whites:
        white_ranges.insert(0, '- Görsel olarak incelenen aralıkların başlangıç ve süreleri aşağıda yer alıyor.')
        review=WORK/'visual-qa/white-review.json'
        if review.is_file():
            observed=json.loads(review.read_text())
            intervals=[[entry['start'],entry['duration']] for entry in whites]
            if observed.get('sha256')==digest and observed.get('pictureSha256')==result.get('pictureSha256') and observed.get('intervals')==intervals:
                white_ranges.append(f"- Beyaz alanlar için {observed['samples']} kare incelendi. {observed['summary']} Son görsel inceleme sayfası bu adayların orta karelerini de içeriyor.")
        white_ranges.append('- Bu tarama bütün uygulama alanını ölçer. Açık renkli bir sayfadaki tek bir boş paneli ayrıca sınıflandırmaz.')

    ocr=result['screenPrivacy']
    if ocr['available']:
        privacy_note=(f"Tesseract, nihai MP4’te oturum açma, davet, bağlantı ve hesap güvenliği işlemlerinden "
                      f"{len(ocr['scenes'])} sahnenin {ocr['frames']} örnek karesini okudu. "
                      "Okunan metinde bilinen demo parolası, oturum anahtarı veya davet ve parola yenileme bağlantısı saptanmadı. "
                      "OCR denetimi örneklenen karelerde okunabilen metni kapsar.")
    else:
        privacy_note='Bu üretimde Tesseract bulunmadığı için nihai karelerde hassas alan OCR denetimi çalıştırılamadı.'
    widths=result.get('captionWidths')
    layout_note=(f"- Arial yazı tipiyle ölçülen en geniş altyazı {widths['subtitle']} / 1390 piksel, en geniş kalın bölüm adı {widths['title']} / 448 piksel." if widths else None)
    audio_notes=[]
    evidence=WORK/'audio/final-mix-qa.json'
    if evidence.is_file():
        mix=json.loads(evidence.read_text())
        if mix.get('video_sha256')==digest and mix.get('manifest_sha256')==sha256_file(OUT/'scenes.json') and mix.get('passed'):
            audio_notes.append(f"- Nihai AAC akışındaki {mix['checked_clips']} konuşma parçasının ses şiddeti eğrisi kaynak WAV ile eşleştirildi. En düşük korelasyon {mix['min_envelope_correlation']:.4f}, en büyük zaman kayması {mix['max_abs_offset_ms']} ms. Son sözden sonra {mix['tail_after_last_clip_ms']} ms ses payı var.")
            pace=str(mix['words_per_narrated_minute']).replace('.',',')
            audio_notes.append(f"- Kaynak ses parçalarının sürelerine göre anlatım {pace} kelime/dakika. Başlangıç temposu için belirtilen aralık 135–155 kelime/dakika.")
            transcriptions=mix.get('asr_samples',[])
            if transcriptions:
                normalized=lambda text:' '.join(re.findall(r'\w+',text.casefold()))
                matched=sum(normalized(x['transcript'])==normalized(x['text']) for x in transcriptions)
                variants=[term for term in ('AW Center','JIRA','Excel','PDF','DOORS') if any(term.casefold() in x['text'].casefold() and term.casefold() not in x['transcript'].casefold() for x in transcriptions)]
                words=(', '.join(variants)+' en az bir örnekte farklı yazıldı.') if variants else ''
                audio_notes.append(f"- Çevrimdışı Türkçe konuşma tanıma, nihai sesten {len(transcriptions)} parçayı yazıya çevirdi. Büyük/küçük harf ve noktalama birleştirilince {matched} sonuç kaynak metinle birebir eşleşti. {words} Telaffuz değerlendirmesinin bu kısmı otomatik metin karşılaştırmasıdır.")
    reviewed=[]
    for note in sorted((WORK/'visual-qa').glob('review-*.json')):
        record=json.loads(note.read_text())
        if record.get('sha256')!=digest:continue
        if not record.get('sheets') or not set(record['sheets'])<=set(result['sheets']):continue
        reviewed.append(f"- {', '.join(record['sheets'])} · {record['summary']}")
    reviewed.sort()
    file_rows=[f"| {entry['scene']} | {entry['file'].replace('|','·')} | {entry['format']} | {entry['bytes']:,} |" for entry in result['downloads']]

    report=[
        '# AW Center tanıtımı · kalite raporu','',
        f"MP4 süresi **{clock(result['seconds'])}**. Dosya **{result['bytes']/1e6:.1f} MB**. Son montajda **{result['chapters']} sahne**, **{result['beats']} işlem ve sonuç aralığı**, **{srt_count} altyazı parçası** var.",'',
        '## Görüntü, ses ve zamanlama','',
        '- FFprobe görüntüyü 1920 × 1080, 30 FPS, H.264 ve yuv420p olarak doğruladı. Ses AAC, 48 kHz ve mono. FFmpeg her iki akışı baştan sona hata denetimiyle çözdü.',
        f"- Son AAC akışının ölçülen bütünleşik seviyesi {result['lufs']} LUFS, gerçek tepe değeri {result['truePeak']} dBTP. Kabul aralığı −16 ± 1,5 LUFS ve en fazla −1,5 dBTP. Anlatım parçalarının sonları kaynak süreleriyle karşılaştırıldı.",
        f"- Chromium, {result['playbackChapters']} bölümün giriş, etkileşim ve doğrulanmış son sonuç anlarında toplam {result['playbackSamples']} oynatma başlattı. Her örnekte medya saati ilerledi ve doğal görüntü 1920 × 1080 ölçüldü. Tarayıcı oynatma deneyi sessiz modda yürütüldü.",
        f"- Son MP4’ten bölüm başlarında ve doğrulanan sonuçlarda {result['sampledFrames']} kare çıkarıldı. 0,3 saniye ve üzeri siyah görüntü aralığı saptanmadı.",
        *audio_notes,
        '- '+pause_note,
        '- '+white_note,
        *white_ranges,
        '- SRT içindeki her metin bir veya iki satır. Altyazılar, CSV işlem aralıkları, MP4 bölüm işaretleri ve chapters.txt, son montaj zaman çizelgesiyle ayrı ayrı karşılaştırıldı.',
        *([layout_note] if layout_note else []),
        '- Altyazı ve bölüm adı uygulama görüntüsünün altındaki 112 piksellik bantta. İmleç, gerçek pointer olaylarından çiziliyor. Simülasyon kullanılan sahnelerde alt bantta “Temsili sonuç” yazıyor.','',
        '## Kare incelemesi','',
        *(reviewed or ['Nihai kareler bölüm başlangıçları ve işlem sonuçları için çıkarıldı. Bu dosyanın üretildiği anda karelere ait ayrı görsel inceleme notu kaydedilmemişti.']),'',
        '- '+privacy_note,
        f"- Yayımlanan metinler, sahne kayıt bilgileri ve özel tanılama kayıtlarından {result['privateTextFiles']} dosya bilinen demo kimlik bilgileri ve erişim bağlantısı kalıplarıyla tarandı. Eşleşme bulunmadı.",'',
        '## İşlem ve dosya kanıtı','',
        f"- Kayda bağlanan {len(result['downloads'])} indirme olayı açıldı ve dosya içeriği denetlendi. DOCX, XLSX, PDF, ZIP, JSON ve görsel kontrolleri dosya türüne göre uygulandı. ZIP içindeki Office ve PDF üyeleri de denetlendi.",
        '- Atlas çevirisinin ilk başlığı İngilizce karşılığıyla eşleşti. Outlook ekindeki bütün OOXML üyeleri, örnek Word belgesinin karşılık gelen üyeleriyle SHA-256 düzeyinde eşleşti. Dönüştürülen görselin genişliği 640 piksel.',
        '', '| Sahne | İndirilen dosya | Biçim | Bayt |', '|---|---|---|---:|', *file_rows, '',
        '- Sunucu denetimleri oturum ve CSRF, kullanıcıya ait çıktı erişimi, kapalı e-posta taşıması ve dış bağlantının engellenmesini içeriyor. Tarayıcının beklenmeyen origin isteği sahneyi başarısız kılar.',
        '- Kontroller, izole üretim hattını ve videoda kullanılan ürün akışlarını kapsıyor.','',
        '## Kapsam ve sınırlamalar','',
        'Kapsam tablosundaki açık satırlar aşağıda yer alıyor. Aynı bileşenin proje veya veri türüne göre yinelenen görünümleri ortak satırlarda gruplandı. Windows yönetici kurulum aracı ve üretim dağıtımı, tarayıcıdaki ürün tanıtımının dışındadır.','',
        *[f"- **{r[4]}** — {r[7] or r[8] or r[-1]}" for r in gaps], '',
        'İşletim sistemi dosya seçicileri kayda girmez. Seçilen dosya, uygulamanın yükleme alanında ve işlem sonucunda görünür. Kurumsal sistemlerin canlı gecikmesi ve dış sistemdeki son durum bu kayıtla ölçülmedi.',
        'İşitsel incelemenin sınırı ve Türkçe örneğin çevrimdışı konuşma tanıma sonucu ses seçimi notunda belgelenmiştir. İnsan dinleyiciyle baştan sona telaffuz onayı yapılmadı.','',
        '## Dosya bütünlüğü','',f'SHA-256 {digest}',''
    ]
    (OUT/'qa-report.md').write_text('\n'.join(report))
if __name__=='__main__':main()
