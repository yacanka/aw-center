"""Build, seed, record, render and verify the isolated AW Center Turkish tour."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = ROOT / 'artifacts/aw-center-video/.work'
PORT = 18765
BASE = f'http://127.0.0.1:{PORT}'
ENV = {**os.environ, 'AW_VIDEO_DEMO':'1'}
PYTHON = sys.executable
BACKEND = [PYTHON, str(HERE / 'backend_demo/run.py')]

def run(*command, **options):
    sp.run([str(c) for c in command],check=True,cwd=ROOT,env=ENV,**options)

def ready():
    try:
        with urlopen(BASE+'/health/live/',timeout=.8) as response:
            return response.status==200
    except (OSError,URLError):
        return False

def frontend():
    frontend_root=ROOT/'frontend'
    build_key=hashlib.sha256()
    for source in sorted([*frontend_root.glob('src/**/*'),*frontend_root.glob('public/**/*'),frontend_root/'index.html', frontend_root/'package-lock.json', frontend_root/'vite.config.ts']):
        if source.is_file():
            build_key.update(str(source.relative_to(frontend_root)).encode())
            build_key.update(source.read_bytes())
    stamp=WORK/'frontend-key'
    if (WORK/'dist/index.html').exists() and stamp.exists() and stamp.read_text()==build_key.hexdigest():return
    sp.run(['node',frontend_root/'scripts/build-mermaid-renderer.mjs'],check=True,cwd=frontend_root,env=ENV)
    sp.run([frontend_root/'node_modules/.bin/vite','build',frontend_root,'--outDir',WORK/'dist','--emptyOutDir'],check=True,cwd=ROOT,env={**ENV,'VITE_API_URL':'/','VITE_APP_TITLE':'AW Center','VITE_VERSION':'1.1.0'})
    stamp.write_text(build_key.hexdigest())

def main():
    WORK.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(HERE/'delivery-readme.md',WORK.parent/'README.md')
    for binary in ['ffprobe','ffmpeg','node']:
        if not shutil.which(binary):raise SystemExit(f'Required binary missing: {binary}')
    if ready():raise SystemExit(f'Port {PORT} is already in use. Stop the existing recording server first.')
    frontend()
    run(PYTHON,HERE/'audio/setup.py','--with-asr')
    run(PYTHON,HERE/'audio/tour_audio.py')
    run(*BACKEND,'check')
    run(*BACKEND,'reset')
    logfile=WORK/'service.log'
    with logfile.open('w') as log:
        server=sp.Popen(BACKEND+['serve'],cwd=ROOT,env=ENV,stdout=log,stderr=sp.STDOUT)
        try:
            for _ in range(160):
                if server.poll() is not None:raise RuntimeError(f'Demo server exited. See {logfile}')
                if ready():break
                time.sleep(.25)
            else:raise TimeoutError('Demo server readiness timed out')
            run('node',HERE/'record.mjs','record','pilot')
            run(PYTHON,HERE/'render.py','--pilot')
            run('node',HERE/'playback.mjs','--pilot')
            run('node',HERE/'record.mjs','record')
        finally:
            server.terminate()
            try:server.wait(timeout=25)
            except sp.TimeoutExpired:
                server.kill()
                server.wait()
    run(PYTHON,HERE/'render.py')
    run('node',HERE/'playback.mjs')
    run(PYTHON,HERE/'backend_demo/verify_downloads.py')
    run(PYTHON,HERE/'audio/verify_mix.py','--with-asr')
    run(PYTHON,HERE/'qa.py')
if __name__=='__main__':
    main()
