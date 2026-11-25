"""Build the downloadable Windows x64 template after npm run build:viewer."""

import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != 'nt' or sys.version_info[:2] != (3, 11) or struct.calcsize('P') != 8:
        raise SystemExit('Build the Windows x64 template with 64-bit CPython 3.11 on Windows.')
    assets = ROOT / 'frontend/dist-viewer'
    if not (assets / 'index.html').is_file():
        raise SystemExit('First run npm --prefix frontend run build:viewer.')
    if b'__DASHBOARD_SESSION__' not in (assets / 'index.html').read_bytes():
        raise SystemExit('The viewer build does not contain the browser session placeholder.')
    sys.path.insert(0, str(ROOT / 'backend'))
    from compliance.executable_config import mark_executable_template

    output = ROOT / 'packaging/dist'
    output.mkdir(parents=True, exist_ok=True)
    # Stage next to the served template. A failed or concurrent build cannot truncate a download.
    with TemporaryDirectory(prefix='viewer-build-', dir=output) as temporary:
        stage = Path(temporary)
        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
            '--noupx', '--name', 'CertificationDashboard', '--paths', str(ROOT),
            '--paths', str(ROOT / 'backend'), '--distpath', str(stage),
            '--workpath', str(stage / 'work'), '--specpath', str(stage),
            '--add-data', f'{assets};viewer', str(ROOT / 'scripts/certification_viewer/entrypoint.py'),
        ], cwd=ROOT, check=True)
        executable = stage / 'CertificationDashboard.exe'
        mark_executable_template(executable)
        os.replace(executable, output / executable.name)
    print('Built packaging/dist/CertificationDashboard.exe')


if __name__ == '__main__':
    main()
