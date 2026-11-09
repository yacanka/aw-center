"""Verified portable source payloads and immutable production release staging.

A source manifest detects transfer corruption and local source changes. It is not
an authenticity signature: distribute the outer ZIP checksum over a trusted
channel. Existing release source is checked before reuse and never repaired.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

from scripts.launcher.installation_bundle import (
    GENERATED_SOURCE_DIRECTORIES, _json_object, _relative_path, copy_install_source, install_inventory,
)
from scripts.launcher.installation_permissions import require_private, require_unlinked, secure_path
from scripts.launcher.installation_state import installation_lock, private_directory
from scripts.launcher.model import LauncherError, Project
from scripts.launcher.offline_manifest import file_sha256

SOURCE_MANIFEST = 'manager-source-manifest.json'
MANAGER_SOURCE_FILES = (
    'AWCenterManager.pyw',
    'scripts/build_manager.py',
    'packaging/manager.spec', 'packaging/manager-requirements.txt',
    'backend/users/initial_admin.py',
    'scripts/launcher/system_python.py',
    'scripts/launcher/installation_env.py',
    'scripts/launcher/probe_budget.py', 'scripts/launcher/runtime_selection.py',
    'scripts/launcher/resource_locks.py',
    'scripts/launcher/production_build.py',
    'scripts/launcher/installation_backup.py', 'scripts/launcher/installation_connection.py',
    *(f'scripts/manager/{name}.py' for name in (
        '__init__', 'main', 'controller', 'worker', 'transport', 'payload', 'view', 'view_model', 'view_theme',
        'paths', 'task_policy', 'operations', 'source_checks', 'preferences', 'distribution', 'bundle_preparation', 'inspection', 'ensure')),
)
REQUIRED_SOURCE_FILES = {
    'launcher.py', 'AWCenter.cmd', 'backend/manage.py', 'requirements.txt',
    'frontend/package.json', 'frontend/package-lock.json',
    'scripts/launcher/installation_sources.py', 'scripts/launcher/installation_catalog.json',
    'scripts/launcher/installation_python.sha256',
    'scripts/launcher/installation_python_startup.sha256',
    'scripts/launcher/installation_verify_python.py',
}
GENERATED_DIRECTORIES = {
    *GENERATED_SOURCE_DIRECTORIES,
    ('.venv',), ('.runtime',), ('frontend', 'node_modules'), ('frontend', 'dist'),
    ('frontend', 'test-results'), ('frontend', 'playwright-report'),
    ('backend', 'static'), ('backend', 'staticfiles'), ('backend', 'private_media'),
    ('backend', 'media'), ('backend', 'cache'),
}
GENERATED_FILES = {
    'backend/db.sqlite3', 'backend/db.sqlite3-wal', 'backend/db.sqlite3-shm',
    # A stopped SQLite writer can leave rollback data for the next connection.
    # Verification must neither classify it as source nor delete recovery data.
    'backend/db.sqlite3-journal',
}


class ProductionSourceNotPrepared(LauncherError):
    code = 'production_source_not_prepared'
    remedy = ('Mevcut prod kurulumunu kullanmak için Proje kaynak dizini alanını boş bırakın; '
              'kayıtlı kaynak otomatik seçilir. İlk kurulum için AW Center’ı aç işlemini kullanın. '
              'Mevcut prod profilini veya veritabanını silmeyin.')

    def __init__(self):
        super().__init__('Seçilen kaynak sürümü için hazırlanmış bir prod kopyası bulunamadı; '
                         'kaynak paketi doğrulandı, mevcut kurulum değiştirilmedi.')


def default_source_root() -> Path:
    """Use source beside the portable EXE; development uses this repository."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).absolute().parent / 'source'
    return Path(__file__).resolve().parents[2]


def _generated(relative: Path) -> bool:
    return ('__pycache__' in relative.parts or relative.suffix == '.pyc' or
            relative.as_posix() in GENERATED_FILES or
            any(relative.parts[:len(parts)] == parts for parts in GENERATED_DIRECTORIES))


def _source_inventory(source: Path) -> list[dict]:
    """Hash exact source while allowing only declared generated runtime state."""
    require_unlinked(source)
    if not source.is_dir():
        raise LauncherError('Manager source directory is unavailable')
    artifacts = []
    names = set()
    for current, directories, files in os.walk(source, followlinks=False):
        base = Path(current)
        directories[:] = [name for name in directories if not _generated((base / name).relative_to(source))]
        for name in directories:
            require_unlinked(base / name)
        for name in files:
            path = base / name
            relative = path.relative_to(source)
            if relative.as_posix() == SOURCE_MANIFEST or _generated(relative):
                continue
            require_unlinked(path)
            _relative_path(relative.as_posix())
            if not stat.S_ISREG(path.stat().st_mode):
                raise LauncherError('Manager source must contain only regular files')
            folded = relative.as_posix().casefold()
            if folded in names:
                raise LauncherError('Manager source contains duplicate Windows paths')
            names.add(folded)
            artifacts.append({'path': relative.as_posix(), 'size': path.stat().st_size,
                              'sha256': file_sha256(path)})
    return sorted(artifacts, key=lambda entry: entry['path'])


def _fingerprint(artifacts: list[dict]) -> str:
    return hashlib.sha256(json.dumps(artifacts, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def _validate_manifest(manifest: dict) -> list[dict]:
    if set(manifest) != {'format_version', 'fingerprint', 'artifacts'} or manifest.get('format_version') != 1:
        raise LauncherError('Manager source manifest version is invalid')
    artifacts = manifest['artifacts']
    if not isinstance(artifacts, list):
        raise LauncherError('Manager source inventory is invalid')
    names = set()
    for entry in artifacts:
        if not isinstance(entry, dict) or set(entry) != {'path', 'size', 'sha256'}:
            raise LauncherError('Manager source inventory is invalid')
        relative = _relative_path(entry['path'])
        if (relative.as_posix() == SOURCE_MANIFEST or _generated(relative) or
                entry['path'].casefold() in names or type(entry['size']) is not int or entry['size'] < 0 or
                not isinstance(entry['sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) is None):
            raise LauncherError('Manager source inventory is invalid')
        names.add(entry['path'].casefold())
    if not REQUIRED_SOURCE_FILES.issubset({entry['path'] for entry in artifacts}):
        raise LauncherError('Manager source is incomplete')
    ordered = sorted(artifacts, key=lambda entry: entry['path'])
    if manifest['fingerprint'] != _fingerprint(ordered):
        raise LauncherError('Manager source fingerprint verification failed')
    return ordered


def verify_source_payload(source: Path) -> dict:
    """Verify a transferred or already staged source, without modifying it."""
    source = Path(source).absolute()
    require_unlinked(source / SOURCE_MANIFEST)
    manifest = _json_object(source / SOURCE_MANIFEST)
    expected = _validate_manifest(manifest)
    if expected != _source_inventory(source):
        raise LauncherError('Manager source checksum verification failed; source was not changed')
    return manifest


def prepare_source_payload(project: Project, destination: Path) -> dict:
    """Copy the launcher's safe source selection and reviewed GUI module names."""
    destination = Path(destination).absolute()
    require_unlinked(destination)
    copy_install_source(project, destination)
    # copy_install_source deliberately accepts extracted .py files. Narrow the
    # new manager subtree to explicit application modules, including in a dirty
    # development checkout whose new manager files are not Git-tracked yet.
    manager = destination / 'scripts' / 'manager'
    if manager.exists():
        shutil.rmtree(manager)
    for relative in MANAGER_SOURCE_FILES:
        source = project.root / relative
        require_unlinked(source)
        if not source.exists():
            continue
        if not source.is_file():
            raise LauncherError('Manager application source must be a regular file')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Reuse the installation-bundle inventory implementation on this fresh tree;
    # no generated state exists here, so every copied byte must be represented.
    artifacts = install_inventory(destination)
    manifest = {'format_version': 1, 'fingerprint': _fingerprint(artifacts), 'artifacts': artifacts}
    _validate_manifest(manifest)
    (destination / SOURCE_MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return verify_source_payload(destination)


def _copy_verified_source(source: Path, target: Path, manifest: dict) -> None:
    target.mkdir()
    secure_path(target)
    for entry in manifest['artifacts']:
        relative = _relative_path(entry['path'])
        original = source / relative
        require_unlinked(original)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
    shutil.copy2(source / SOURCE_MANIFEST, target / SOURCE_MANIFEST)
    if verify_source_payload(target) != manifest:
        raise LauncherError('Manager source changed during its verified copy')


def production_source_path(home: Path, fingerprint: str) -> Path:
    """Keep Windows package paths short; the manifest retains the full SHA-256.

    A directory-prefix collision is rejected by full manifest verification.
    Existing full-digest releases remain supported without moving their venvs.
    """
    return home / 'r' / fingerprint[:12]


def _stage_verified(source: Path, home: Path) -> Path:
    manifest = verify_source_payload(source)  # Validate before creating home.
    with installation_lock(home):
        releases = private_directory(home / 'r', root=home)
        target = production_source_path(home, manifest['fingerprint'])
        release = target
        require_unlinked(target)
        if release.exists():
            if verify_source_payload(target) != manifest:
                raise LauncherError('Existing production release differs from the selected source')
            return target
        with tempfile.TemporaryDirectory(prefix='.manager-release-', dir=releases) as temporary:
            staging = Path(temporary) / 'release'
            _copy_verified_source(source, staging, manifest)
            # The installation lock serializes publishers. On the Windows target
            # rename also refuses any existing destination, including empty dirs.
            if release.exists():
                raise LauncherError('Production release already exists; source was not overwritten')
            staging.rename(release)
        return target


def _selected_paths(source: Path, home: Path) -> tuple[Path, Path, bool]:
    source, home = Path(source).absolute(), Path(home).absolute()
    require_unlinked(source)
    require_unlinked(home)
    if home.resolve().is_relative_to(source.resolve()):
        raise LauncherError('Manager installation home and selected source must be separate')
    canonical = False
    if source.resolve().is_relative_to(home.resolve()):
        if source.is_relative_to(home / 'r'):
            relative = source.relative_to(home / 'r')
            valid = len(relative.parts) == 1 and re.fullmatch(r'[0-9a-f]{12}', relative.name)
            identity = relative.name
        else:
            relative = source.relative_to(home / 'releases') if source.is_relative_to(home / 'releases') else Path()
            valid = (len(relative.parts) == 2 and relative.parts[1] == 'source'
                     and re.fullmatch(r'[0-9a-f]{64}', relative.parts[0]))
            identity = relative.parts[0] if valid else ''
        if not valid:
            raise LauncherError('Selected production source must use the canonical release path')
        manifest = verify_source_payload(source)
        if identity not in {manifest['fingerprint'], manifest['fingerprint'][:12]}:
            raise LauncherError('Production source fingerprint differs from its canonical path')
        require_private(home)
        canonical = True
    return source, home, canonical


@contextmanager
def _selected_source(source: Path):
    if (source / SOURCE_MANIFEST).exists():
        verify_source_payload(source)
        yield source
        return
    if not (source / '.git').exists():
        raise LauncherError('Extracted manager source requires its checksum manifest')
    project = Project(source, source / 'backend/manage.py', source / 'frontend/package.json', source / 'requirements.txt')
    with tempfile.TemporaryDirectory(prefix='awcenter-manager-source-') as temporary:
        selected = Path(temporary).resolve() / 'source'
        prepare_source_payload(project, selected)
        yield selected


def resolve_production_source(source: Path, home: Path) -> Path:
    """Resolve only an existing verified canonical release; never create state."""
    source, home, canonical = _selected_paths(source, home)
    if canonical:
        return source
    with _selected_source(source) as selected:
        manifest = verify_source_payload(selected)
        target = production_source_path(home, manifest['fingerprint'])
        require_unlinked(target)
        if not target.exists():
            target = home / 'releases' / manifest['fingerprint'] / 'source'
            require_unlinked(target)
            if not target.exists():
                raise ProductionSourceNotPrepared()
        if verify_source_payload(target) != manifest:
            raise LauncherError('Existing production release differs from the selected source')
        return target


def stage_production_source(source: Path, home: Path) -> Path:
    """Stage source at home/r/<short-id>, never overwrite.

    A development Git checkout is first reduced to the safe release selection.
    Every extracted source must already carry its exact source checksum manifest.
    Only declared generated state is ignored while verifying an existing release.
    """
    source, home, canonical = _selected_paths(source, home)
    if canonical:
        return source
    with _selected_source(source) as selected:
        return _stage_verified(selected, home)
