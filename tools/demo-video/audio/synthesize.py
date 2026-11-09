"""Generate offline Turkish narration. Batch input is a JSON list of {text, output}."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'artifacts/aw-center-video/.work/audio'
REVISION = '0965f4a5fb578763be8ca2a2bb39421378471cd1'
VOICE = 'Antalia-2 Mini 1.0.1'
SPEED = 0.94
SEED = 11
WORDS = {
    'AW Center': 'ey dabılyu sentır', 'JIRA': 'ciyra', 'Excel': 'eksel',
    'Word': 'vörd', 'DOORS': 'dorz', 'Teamcenter': 'tiim sentır',
    'DocProof': 'dok pruf', 'PDF': 'pe de fe', 'Outlook': 'autluk',
    'Watcher': 'voçır', 'Worklog': 'vörk log', 'CSV': 'ce se ve',
    'DOCX': 'dok iks', 'XLSX': 'iks el es iks', 'PowerPoint': 'pavır poynt',
}
BRANDS = re.compile(r'(?<!\w)(' + '|'.join(map(re.escape, WORDS)) + r')(?!\w)', re.IGNORECASE)
READINGS = {k.casefold(): v for k, v in WORDS.items()}
SAMPLE = ('AW Center üzerinden kurgusal proje kayıtlarını birlikte inceleyelim. Önce dosyayı seçiyor, '
          'ardından işi başlatıyoruz. 101 numaralı belge için hazırlanan liste artık hazır. JIRA kaydını '
          've Excel tablosundaki son durumu görebiliriz. Bu örnekte güncellenen belgeyi açıp değişen '
          'alanları kontrol edeceğiz. Tarihler ve isimler bu tanıtım için hazırlanmıştır.')


def pronunciations(text):
    return BRANDS.sub(lambda m: READINGS[m.group(0).casefold()], text)


def wav_info(path):
    with wave.open(str(path), 'rb') as wav:
        if wav.getframerate() != 48000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f'Unexpected WAV format in {path.name}')
        frames = wav.getnframes()
        if frames <= 0 or len(wav.readframes(frames)) != frames * 2:
            raise ValueError(f'Incomplete WAV: {path.name}')
        return frames / wav.getframerate()


def atomic_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dst.parent, suffix='.part', delete=False) as temp:
        tmp_path = Path(temp.name)
    try:
        shutil.copyfile(src, tmp_path)
        os.replace(tmp_path, dst)
    finally:
        tmp_path.unlink(missing_ok=True)


def render(requests):
    cache = WORK / 'clips'
    cache.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(WORK / 'packages'))
    model = None
    manifest = []
    for request in requests:
        text = request['text'].strip()
        if not text:
            raise ValueError('Narration text is empty')
        spoken = pronunciations(request.get('pronunciation') or text)
        key = hashlib.sha256(json.dumps([REVISION, SPEED, SEED, spoken], ensure_ascii=False).encode()).hexdigest()
        cached = cache / (key + '.wav')
        if not cached.exists():
            if model is None:
                from antalia_mini import Antalia
                model = Antalia(WORK / 'models', device='cpu', threads=2, warmup=False)
            with tempfile.NamedTemporaryFile(dir=cache, suffix='.wav', delete=False) as temp:
                tmp_path = Path(temp.name)
            try:
                model.say(spoken, path=tmp_path, seed=SEED, speed=SPEED)
                wav_info(tmp_path)
                os.replace(tmp_path, cached)
            finally:
                tmp_path.unlink(missing_ok=True)
        duration = wav_info(cached)
        destination = Path(request['output']).resolve()
        if cached.resolve() != destination:
            atomic_copy(cached, destination)
        manifest.append(dict(text=text, pronunciation=spoken, output=str(destination),
                             seconds=duration, voice=VOICE, sample_rate=48000, channels=1, seed=SEED))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text')
    source.add_argument('--batch', type=Path)
    source.add_argument('--sample', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.batch:
        requests = json.loads(args.batch.read_text(encoding='utf-8'))
    else:
        if not args.output and not args.sample:
            parser.error('--text requires --output')
        requests = [dict(text=SAMPLE if args.sample else args.text, output=args.output or WORK / 'sample.wav')]
    print(json.dumps(render(requests), ensure_ascii=False))


if __name__ == '__main__':
    main()
