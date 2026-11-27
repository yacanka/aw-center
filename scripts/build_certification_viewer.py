"""Build the downloadable Windows x64 template after npm run build:viewer."""

import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

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


def write_tk_archive(path, environment):
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for variable, destination in (('TCL_LIBRARY', '_tcl_data'), ('TK_LIBRARY', '_tk_data')):
            library = Path(environment[variable])
            for file in sorted(library.rglob('*')):
                if file.is_file():
                    archive.write(file, Path(destination) / file.relative_to(library))


def main():
    if os.name != 'nt' or sys.version_info[:2] != (3, 11) or struct.calcsize('P') != 8:
        raise SystemExit('Build the Windows x64 template with 64-bit CPython 3.11 on Windows.')
    assets = ROOT / 'frontend/dist-viewer'
    if not (assets / 'index.html').is_file():
        raise SystemExit('First run npm --prefix frontend run build:viewer.')
    if b'__DASHBOARD_SESSION__' not in (assets / 'index.html').read_bytes():
        raise SystemExit('The viewer build does not contain the browser session placeholder.')
    sys.path.insert(0, str(ROOT / 'backend'))
    from PyInstaller.archive.readers import CArchiveReader
    from compliance.executable_config import mark_executable_template

    environment = tcl_tk_build_environment()
    probe = subprocess.run([
        sys.executable, '-c',
        "import tkinter; window = tkinter.Tk(); print(window.tk.call('info', 'patchlevel')); window.destroy()",
    ], env=environment, capture_output=True, text=True, errors='replace')
    if probe.returncode:
        raise SystemExit(f'Build Python Tcl/Tk startup check failed:\n{probe.stderr.strip()}')
    print(f'Build Python Tcl version: {probe.stdout.strip()}', flush=True)
    output = ROOT / 'packaging/dist'
    output.mkdir(parents=True, exist_ok=True)
    # Stage next to the served template. A failed or concurrent build cannot truncate a download.
    with TemporaryDirectory(prefix='viewer-build-', dir=output) as temporary:
        stage = Path(temporary)
        tk_archive = stage / 'viewer-tk.zip'
        write_tk_archive(tk_archive, environment)
        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
            '--noupx', '--name', 'CertificationDashboard', '--paths', str(ROOT),
            '--paths', str(ROOT / 'backend'), '--distpath', str(stage),
            '--workpath', str(stage / 'work'), '--specpath', str(stage),
            '--add-data', f'{assets};viewer',
            '--add-data', f'{environment["TCL_LIBRARY"]};_tcl_data',
            '--add-data', f'{environment["TK_LIBRARY"]};_tk_data',
            '--add-data', f'{tk_archive};.',
            str(ROOT / 'scripts/certification_viewer/entrypoint.py'),
        ], cwd=ROOT, env=environment, check=True)
        executable = stage / 'CertificationDashboard.exe'
        archive_paths = {name.replace('\\', '/') for name in CArchiveReader(str(executable)).toc}
        missing = {'_tcl_data/init.tcl', '_tk_data/tk.tcl', 'viewer-tk.zip'} - archive_paths
        if missing:
            raise SystemExit(f'EXE archive is missing Tcl/Tk files: {", ".join(sorted(missing))}')
        try:
            subprocess.run([executable, '--check-tk'], cwd=stage, check=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            report = stage / 'tk-startup-error.txt'
            detail = (report.read_text(encoding='utf-8').strip() if report.is_file()
                      else f'Viewer exited with code {exc.returncode} before reporting a Tcl/Tk error.')
            raise SystemExit(f'Packaged Tcl/Tk startup check failed (startup files are in the EXE archive):\n{detail}') from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SystemExit(f'Packaged Tcl/Tk startup check failed: {exc}') from exc
        mark_executable_template(executable)
        os.replace(executable, output / executable.name)
    print('Built packaging/dist/CertificationDashboard.exe')


if __name__ == '__main__':
    main()
