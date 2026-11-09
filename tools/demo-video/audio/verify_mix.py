"""Verify narration against the decoded release MP4 and optionally transcribe Turkish excerpts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import wave

import numpy as np

from synthesize import WORK
from setup import ASR_MODEL, ASR_SHA256

RATE = 16000
OUT = WORK.parents[1]
MIN_CORRELATION = .90
MAX_OFFSET_MS = 100


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def pcm(source):
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(source), '-map', '0:a:0',
               '-vn', '-ac', '1', '-ar', str(RATE), '-f', 's16le', 'pipe:1']
    return np.frombuffer(subprocess.check_output(command), dtype='<i2')


def envelope(samples, rate):
    block = rate // 100
    used = len(samples) // block * block
    chunk = block * 3000
    result = np.empty(used // block, dtype=np.float32)
    for first in range(0, used, chunk):
        end = min(used, first + chunk)
        matrix = samples[first:end].astype(np.float32).reshape(-1, block)
        # Log RMS tolerates the final loudness adjustment while preserving speech timing.
        result[first // block:end // block] = np.log1p(np.sqrt(np.mean(np.square(matrix), axis=1)))
    return result


def channel_envelope(path):
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError(f'Unexpected narration format in {path.name}')
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
        return envelope(samples, wav.getframerate())


def match(reference, mix, start):
    anchor = int(round(start * 100))
    reference = reference - reference.mean()
    norm = np.linalg.norm(reference)
    candidates = []
    for delta in range(-28, 29):
        offset = anchor + delta
        if offset < 0 or offset + len(reference) > len(mix):
            continue
        fragment = mix[offset:offset + len(reference)]
        centered = fragment - fragment.mean()
        denom = norm * np.linalg.norm(centered)
        if denom > 0:
            candidates.append((float(np.dot(reference, centered) / denom), delta))
    if not candidates:
        raise RuntimeError(f'No audio near {start:.2f} seconds')
    peak, shift = max(candidates)
    return round(peak, 4), shift * 10


def select_tests(segments):
    choices = [segments[0], segments[len(segments) // 2], segments[-1]]
    for term in ('JIRA', 'Excel', 'PDF', 'DOORS'):
        options = [item for item in segments if re.search(rf'\b{term}\b', item['text'], re.I)
                   and item['duration'] >= 3.0]
        if options:
            choices.append(options[len(options) // 2])
    return sorted({item['start']: item for item in choices}.values(), key=lambda item: item['start'])


def transcribe(model_path, segments, audio):
    sys.path.insert(0, str(WORK / 'packages'))
    from pywhispercpp.model import Model
    from importlib.metadata import version

    if digest(model_path) != ASR_SHA256:
        raise ValueError('Unexpected SHA-256 for the multilingual Whisper Small Q5_1 model')
    model = Model(str(model_path), context_params={'use_gpu': False}, language='tr', n_threads=2,
                  print_progress=False, print_realtime=False, print_timestamps=False,
                  redirect_whispercpp_logs_to=None)
    samples = []
    for item in select_tests(segments):
        left = max(0, int((item['start'] - .12) * RATE))
        right = int((item['start'] + item['duration'] + .22) * RATE)
        recognized = model.transcribe(audio[left:right].astype(np.float32) / 32768, no_context=True)
        samples.append({**item, 'transcript': ' '.join(s.text.strip() for s in recognized)})
    return {'asr_model_sha256': ASR_SHA256, 'asr_engine': 'pywhispercpp ' + version('pywhispercpp'),
            'asr_samples': samples}


def compare_scenes(scenes, mix):
    segments = []
    for scene in scenes:
        for beat in scene['beats']:
            for clip in beat['timing']['clips']:
                start = scene['start'] + clip['start']
                corr, shift = match(channel_envelope(OUT / clip['wav']), mix, start)
                segments.append(dict(scene=scene['id'], text=clip['text'], start=round(start, 3),
                                     duration=clip['duration'], envelope_correlation=corr, offset_ms=shift))
    if not segments:
        raise ValueError('No source narration clips found')
    return sorted(segments, key=lambda item: item['start'])


def summary(path, report):
    passed = 'geçti' if report['passed'] else 'inceleme gerektiriyor'
    lines = ['# Son AAC ses kontrolü', '', f"`{report['video']}` dosyasının ses kontrolü {passed}.", '',
             f"- MP4 SHA-256 `{report['video_sha256']}`.", f"- Sahne planı SHA-256 `{report['manifest_sha256']}`.",
             f"- {report['checked_clips']} kaynak WAV, kodlanmış AAC kanalından çözülen sesle karşılaştırıldı.",
             f"- Metinde boşluklarla ayrılmış {report['word_count']} sözcük var. Anlatım WAV’ları toplam "
             f"{report['narration_seconds']:.2f} saniye. Parçaların kendi duraklamaları dahil konuşma hızı "
             f"dakikada {report['words_per_narrated_minute']:.1f} sözcük. Klipler arasındaki bekleme süreleri bu hesaba girmez.",
             f"- En düşük zarf korelasyonu {report['min_envelope_correlation']:.4f}. "
             f"En büyük mutlak kayma {report['max_abs_offset_ms']} ms. Eşik dışı parça sayısı {len(report['low_matches'])}.",
             f"- AAC çözümü {report['decoded_audio_seconds']:.3f} saniye. Son anlatım parçası ile dosya sonu arasında "
             f"{report['tail_after_last_clip_ms']} ms var.",
             f"- 16 kHz mono PCM16 çözümünde sayısal uç değerlere ulaşan örnek sayısı {report['clipped_pcm16_samples']}.", '',
             'Kaynak WAV ve son sesin logaritmik RMS zarfları 10 ms aralıkla karşılaştırılır. Her parça için sahne '
             'planındaki zamanın iki yanında 280 ms aranır. En az 0,90 korelasyon, en fazla 100 ms mutlak kayma, '
             'negatif olmayan kapanış payı ve sıfır doygun PCM16 örneği kabul edilir. Programdaki LUFS ve gerçek '
             'tepe ölçümleri ana kalite raporundadır.', '', '## Konuşma tanıma örnekleri', '']
    if 'asr_samples' in report:
        lines.extend([f"{report['asr_engine']} ve çok dilli Whisper Small Q5_1 son AAC’den seçilen Türkçe kesitleri "
                      f"çevrimdışı çözdü. Model SHA-256 `{report['asr_model_sha256']}`. Başlangıç, orta ve bitiş "
                      'ile seçili ürün adlarının yazıldığı kesitler örneklendi. [Model kaynağı](https://huggingface.co/ggerganov/whisper.cpp/blob/c521a4b02f422512d734391fdf08bb08c0862f68/ggml-small-q5_1.bin)', '',
                      '| Başlangıç (sn) | Sahne | Kaynak metin | Konuşma tanıma çıktısı |', '|---:|---|---|---|'])
        for item in report['asr_samples']:
            escaped = [str(item[k]).replace('|', '\\|').replace('\n', ' ') for k in ('scene', 'text', 'transcript')]
            lines.append(f"| {item['start']:.3f} | {' | '.join(escaped)} |")
    else:
        lines.append('Bu çalıştırmada konuşma tanıma seçeneği kullanılmadı.')
    lines.extend(['', 'Konuşma tanıma yazım ve kelime farkları üretebilir. Doğallık ve telaffuz için insan dinleyici onayı yapılmadı.'])
    if report['low_matches']:
        lines.extend(['', '## İncelenecek parçalar', ''])
        for item in report['low_matches']:
            lines.append(f"- `{item['scene']}`, {item['start']:.3f} sn. Korelasyon {item['envelope_correlation']:.4f}, kayma {item['offset_ms']} ms.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mp4', nargs='?', type=Path, default=OUT / 'AW_Center_Tanitim_TR.mp4')
    parser.add_argument('manifest', nargs='?', type=Path, default=OUT / 'scenes.json')
    parser.add_argument('--json', type=Path, default=WORK / 'final-mix-qa.json')
    parser.add_argument('--summary', type=Path, help='Defaults to audio-qa.md in the MP4 directory')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--asr-model', type=Path)
    group.add_argument('--with-asr', action='store_const', const=ASR_MODEL, dest='asr_model')
    args = parser.parse_args()
    scenes = json.loads(args.manifest.read_text(encoding='utf-8'))
    audio = pcm(args.mp4)
    segments = compare_scenes(scenes, envelope(audio, RATE))
    word_count = sum(len(item['text'].split()) for item in segments)
    narration_seconds = sum(item['duration'] for item in segments)
    end = max(item['start'] + item['duration'] for item in segments)
    low = [x for x in segments if x['envelope_correlation'] < MIN_CORRELATION or abs(x['offset_ms']) > MAX_OFFSET_MS]
    clipped = int(np.count_nonzero(audio == 32767) + np.count_nonzero(audio == -32768))
    tail = round((len(audio) / RATE - end) * 1000)
    report = {'video': args.mp4.name, 'video_sha256': digest(args.mp4), 'manifest_sha256': digest(args.manifest),
              'passed': not low and tail >= 0 and clipped == 0, 'checked_clips': len(segments),
              'decoded_audio_seconds': len(audio) / RATE, 'final_clip_end': round(end, 3),
              'word_count': word_count, 'narration_seconds': round(narration_seconds, 3),
              'words_per_narrated_minute': round(60 * word_count / narration_seconds, 1),
              'tail_after_last_clip_ms': tail, 'sample_interval_ms': 10,
              'max_abs_offset_ms': max(abs(x['offset_ms']) for x in segments),
              'min_envelope_correlation': min(x['envelope_correlation'] for x in segments),
              'low_matches': low, 'clipped_pcm16_samples': int(clipped), 'segments': segments}
    if args.asr_model:
        report.update(transcribe(args.asr_model, segments, audio))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary(args.summary or args.mp4.parent / 'audio-qa.md', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('segments', 'asr_samples', 'low_matches')}, indent=2))
    if not report['passed']:
        raise SystemExit(f'Son ses kontrolü başarısız. Eşik dışı parça sayısı {len(low)}.')


if __name__ == '__main__':
    main()
