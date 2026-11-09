"""Install video-only TTS extras and verify the pinned offline Turkish model."""
import argparse
import hashlib
from importlib.metadata import version
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from synthesize import REVISION, WORK

FILES = {
    'acoustic.safetensors': '72c36a6855ce95dc1d35960a7b61515136813313406e5b9ae1c2ebe6cd2ad428',
    'vocoder.safetensors': '89ca374cc55864b38a36f9ea87c41e1b17376e5d6d68e3a0458332861509bbf6',
    'config.json': 'e22ec7fcbe635dced92070f81e6f1ee83b0d25a23877b0c9ab7fc86e7abe4cd7',
}
ASR_MODEL = WORK / 'models/ggml-small-q5_1.bin'
ASR_SHA256 = 'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
ASR_URL = ('https://huggingface.co/ggerganov/whisper.cpp/resolve/'
           'c521a4b02f422512d734391fdf08bb08c0862f68/ggml-small-q5_1.bin')
ASR_EXTRAS = ['pywhispercpp==1.5.1', 'platformdirs==4.14.5']
# torch, numpy and safetensors are already locked by AW Center itself.
EXTRAS = ['antalia-mini==1.0.1', 'cmudict==1.1.3', 'soundfile==0.14.0', 'cffi==2.1.1',
          'pycparser==3.12', 'importlib-metadata==10.1.0', 'importlib-resources==7.1.0',
          'typing-extensions==4.16.0', 'zipp==4.1.2']


def check_hash(path, digest):
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == digest


def download_model(target, digest, url):
    if check_hash(target, digest):
        return
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        draft = Path(tmp.name)
    try:
        subprocess.run(['curl', '-fsSL', '--retry', '2', '--max-time', '300', url, '-o', str(draft)], check=True)
        if not check_hash(draft, digest):
            raise RuntimeError(f'Model hash mismatch for {target.name}')
        draft.replace(target)
    finally:
        draft.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-asr', action='store_true', help='Also prepare local Turkish transcription for final audio QA')
    args = parser.parse_args()
    packages = WORK / 'packages'
    models = WORK / 'models'
    models.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(packages))
    for name in ['numpy', 'safetensors', 'torch'] + (['requests', 'tqdm'] if args.with_asr else []):
        version(name)
    needed = []
    for spec in EXTRAS + (ASR_EXTRAS if args.with_asr else []):
        name, want = spec.split('==')
        try:
            found = version(name)
        except ModuleNotFoundError:
            found = None
        if found != want:
            needed.append(spec)
    if needed:
        command = [shutil.which('uv') or 'uv', 'pip', 'install', '--python', sys.executable,
                   '--no-deps', '--only-binary', ':all:', '--target', str(packages), *needed]
        subprocess.run(command, check=True)
    for name, digest in FILES.items():
        url = f'https://huggingface.co/cloud0day3/antalia-mini/resolve/{REVISION}/{name}'
        download_model(models / name, digest, url)
    if args.with_asr:
        download_model(ASR_MODEL, ASR_SHA256, ASR_URL)
    print('Türkçe ses paketleri ve model imzaları doğrulandı.')


if __name__ == '__main__':
    main()
