"""Build the downloadable Windows x64 template after npm run build:viewer."""

import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def tcl_tk_build_environment():
    try:
        import _tkinter
    except ImportError as exc:
        raise SystemExit('Install Tcl/Tk and IDLE in the Python 3.11 build interpreter.') from exc

    libraries = Path(sys.base_prefix) / 'tcl'
    environment = os.environ.copy()
    for variable, directory, startup_script in (
        ('TCL_LIBRARY', f'tcl{_tkinter.TCL_VERSION}', 'init.tcl'),
        ('TK_LIBRARY', f'tk{_tkinter.TK_VERSION}', 'tk.tcl'),
    ):
        library = libraries / directory
        if not (library / startup_script).is_file():
            raise SystemExit(f'Missing {library / startup_script}. Repair Tcl/Tk in the Python 3.11 installation.')
        environment[variable] = library.resolve().as_posix()
    return environment


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

    environment = tcl_tk_build_environment()
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
        ], cwd=ROOT, env=environment, check=True)
        executable = stage / 'CertificationDashboard.exe'
        try:
            subprocess.run([executable, '--check-tk'], cwd=stage, check=True, timeout=30)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise SystemExit(f'Packaged Tcl/Tk startup check failed: {exc}') from exc
        mark_executable_template(executable)
        os.replace(executable, output / executable.name)
    print('Built packaging/dist/CertificationDashboard.exe')


if __name__ == '__main__':
    main()
