"""Build the portable Windows x64 manager with an isolated build environment.

This tool never installs PyInstaller into the application's virtual environment.
Run it on Windows with CPython 3.11 including Tk; cross compilation is rejected.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.launcher.installation_bundle import install_inventory
from scripts.launcher.installation_permissions import require_unlinked
from scripts.launcher.installation_sources import SourceSettings, fetch_artifact, load_catalog
from scripts.launcher.model import LauncherError, Project
from scripts.launcher.offline_manifest import file_sha256
from scripts.manager.payload import MANAGER_SOURCE_FILES, prepare_source_payload, verify_source_payload

PYINSTALLER_VERSION = '6.22.3'
MANAGER_MANIFEST = 'manager-manifest.json'
CORE_RUNTIMES = ('python', 'node', 'npm')


def _runtime_metadata(catalog: dict) -> dict:
    return {name: {'version': catalog[name].version, 'filename': catalog[name].filename,
                   'sha256': catalog[name].sha256} for name in CORE_RUNTIMES}


def verify_runtime_payload(directory: Path, metadata: dict) -> None:
    """Reject missing, extra or changed runtime archives against reviewed pins."""
    catalog = load_catalog()
    if any(name not in catalog for name in CORE_RUNTIMES) or metadata != _runtime_metadata(catalog):
        raise LauncherError('Manager runtime metadata differs from the reviewed catalog')
    actual = install_inventory(directory)
    if {entry['path'] for entry in actual} != {catalog[name].filename for name in CORE_RUNTIMES}:
        raise LauncherError('Manager runtime archive set is incomplete or contains unexpected files')
    for name in CORE_RUNTIMES:
        artifact = catalog[name]
        if file_sha256(directory / artifact.filename) != artifact.sha256:
            raise LauncherError('Manager runtime archive checksum verification failed')


def prepare_runtime_payload(directory: Path, settings: SourceSettings) -> dict:
    """Fetch and independently verify only the reviewed Python, Node and npm."""
    directory = Path(directory)
    require_unlinked(directory)
    if directory.exists():
        raise LauncherError('Manager runtime output must not exist')
    catalog = load_catalog()
    if any(name not in catalog for name in CORE_RUNTIMES):
        raise LauncherError('Manager requires reviewed Python, Node and npm runtimes')
    directory.mkdir(parents=True)
    for name in CORE_RUNTIMES:
        original = fetch_artifact(catalog[name], directory, settings)
        target = directory / catalog[name].filename
        if original != target:
            require_unlinked(original)
            shutil.copyfile(original, target)
    metadata = _runtime_metadata(catalog)
    verify_runtime_payload(directory, metadata)
    return metadata


def _archive_outputs(output: Path) -> tuple[Path, Path, Path]:
    return output, output.with_suffix(output.suffix + '.sha256'), output.with_suffix(output.suffix + '.inventory.json')


def _require_new_output(output: Path) -> None:
    require_unlinked(output)
    if output.suffix.lower() != '.zip':
        raise LauncherError('Manager output must have the .zip extension')
    if any(path.exists() for path in _archive_outputs(output)):
        raise LauncherError('Manager archive, checksum and inventory outputs must not exist')


def write_portable_archive(directory: Path, output: Path, metadata: dict) -> None:
    """Publish a ZIP plus SHA-256 and a complete portable byte inventory."""
    output = Path(output).absolute()
    _require_new_output(output)
    if (directory / MANAGER_MANIFEST).exists():
        raise LauncherError('Manager staging manifest already exists')
    artifacts = install_inventory(directory)
    manifest = {**metadata, 'format_version': 1, 'target': 'windows-x64',
                'python': '3.11', 'pyinstaller': PYINSTALLER_VERSION, 'artifacts': artifacts}
    serialized = json.dumps(manifest, sort_keys=True, indent=2) + '\n'
    (directory / MANAGER_MANIFEST).write_text(serialized, encoding='utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in [*artifacts, {'path': MANAGER_MANIFEST}]:
            path = directory / entry['path']
            # Fixed metadata avoids leaking local timestamps, permissions or paths.
            info = zipfile.ZipInfo(entry['path'], date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open('rb') as stream, archive.open(info, 'w', force_zip64=True) as destination:
                shutil.copyfileobj(stream, destination)
    checksum, inventory = _archive_outputs(output)[1:]
    with checksum.open('x', encoding='ascii') as stream:
        stream.write(file_sha256(output) + '  ' + output.name + '\n')
    with inventory.open('x', encoding='utf-8') as stream:
        stream.write(serialized)


def _run_build(command: list[str], *, cwd: Path, env: dict, phase: str, timeout: int = 900) -> None:
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise LauncherError(phase + ' could not complete; build-tool output was withheld') from None
    if result.returncode:
        raise LauncherError(phase + ' failed; build-tool output was withheld to protect package-source credentials')


def build_manager(repository: Path, output: Path, settings: SourceSettings) -> Path:
    """Build only on Windows x64/Python 3.11, without changing app dependencies."""
    if (sys.platform != 'win32' or platform.machine().casefold() not in {'amd64', 'x86_64'} or
            sys.version_info[:2] != (3, 11)):
        raise LauncherError('Manager packaging requires native Windows x64 and CPython 3.11 with Tk')
    repository, output = Path(repository).absolute(), Path(output).absolute()
    _require_new_output(output)
    require_unlinked(repository)
    project = Project(repository, repository / 'backend/manage.py',
                      repository / 'frontend/package.json', repository / 'requirements.txt')
    with tempfile.TemporaryDirectory(prefix='awcenter-manager-build-') as temporary:
        work = Path(temporary).resolve()
        portable = work / 'portable'
        portable.mkdir()
        source_metadata = prepare_source_payload(project, portable / 'source')
        if any(not (portable / 'source' / name).is_file() for name in MANAGER_SOURCE_FILES):
            raise LauncherError('Desktop manager source is incomplete')
        runtimes = prepare_runtime_payload(portable / 'runtimes', settings)
        builder = work / 'builder'
        venv.EnvBuilder(with_pip=True).create(builder)
        python = builder / 'Scripts/python.exe'
        environment = {**os.environ, 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                       'AWCENTER_MANAGER_SOURCE': str(portable / 'source'),
                       'PYINSTALLER_CONFIG_DIR': str(work / 'pyinstaller-cache')}
        environment.pop('PYTHONPATH', None)
        _run_build([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
                    '-r', str(repository / 'packaging/manager-requirements.txt')],
                   cwd=work, env=environment, phase='Isolated manager build dependency installation')
        _run_build([str(python), '-c', 'import tkinter; import PyInstaller; assert PyInstaller.__version__ == "' + PYINSTALLER_VERSION + '"'],
                   cwd=work, env=environment, phase='Python/Tk and pinned PyInstaller verification')
        _run_build([str(python), '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(work / 'dist'), '--workpath', str(work / 'pyinstaller-work'),
                    str(repository / 'packaging/manager.spec')],
                   cwd=work, env=environment, phase='Windowed onedir manager freeze')
        frozen = work / 'dist' / 'AWCenterManager'
        if not (frozen / 'AWCenterManager.exe').is_file() or not (frozen / '_internal').is_dir():
            raise LauncherError('Frozen manager executable or embedded runtime is missing')
        for path in frozen.iterdir():
            require_unlinked(path)
            if path.name not in {'AWCenterManager.exe', '_internal'}:
                raise LauncherError('Frozen manager output contains an unexpected root file')
            shutil.move(str(path), portable / path.name)
        verify_source_payload(portable / 'source')
        verify_runtime_payload(portable / 'runtimes', runtimes)
        write_portable_archive(portable, output, {'source_fingerprint': source_metadata['fingerprint'], 'runtimes': runtimes})
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', help='Explicit runtime archive repository (HTTPS URL or local directory)')
    parser.add_argument('--offline-dir', type=Path)
    parser.add_argument('--ca-file', type=Path)
    parser.add_argument('--source-mode', choices=('online', 'corporate', 'offline'), default='online')
    args = parser.parse_args(argv)
    settings = SourceSettings(repository=args.repository, offline_dir=args.offline_dir,
                              ca_file=args.ca_file, mode=args.source_mode)
    try:
        output = build_manager(args.root, args.output, settings)
    except (LauncherError, OSError, ValueError, subprocess.SubprocessError):
        print('Manager packaging failed; verify native Windows x64/Python 3.11/Tk, reviewed runtime sources and new output paths.', file=sys.stderr)
        return 1
    print(f'Manager archive: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
