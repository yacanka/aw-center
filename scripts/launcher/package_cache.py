"""Private, immutable package acquisitions, separate from installed environments."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from .installation_permissions import require_private, require_unlinked, secure_path
from .installation_state import private_directory
from .model import LauncherError
from .offline_manifest import file_sha256
from .process import OperationCancelled, check_cancelled
from .resource_locks import resource_locks


class PackageCacheError(LauncherError):
    code = 'package_cache_invalid'
    remedy = ('Paket önbelleğini ve kurulum alanının kullanıcıya özel izinlerini kontrol edin; '
              'bozuk önbellek otomatik olarak kullanılmaz veya üzerine yazılmaz.')

    def __init__(self):
        super().__init__('Tamamlanmış paket önbelleğinin bütünlüğü doğrulanamadı.')


def _inventory(directory: Path, *, secure=False) -> dict[str, str]:
    """Hash all bytes and reject links/special files rather than following them."""
    require_unlinked(directory)
    if not directory.is_dir():
        raise PackageCacheError()
    result = {}
    def failed(_):
        raise PackageCacheError()
    for current, directories, files in os.walk(directory, followlinks=False, onerror=failed):
        check_cancelled()
        path = Path(current)
        secure_path(path) if secure else require_private(path)
        for name in directories:
            require_unlinked(path / name)
        for name in files:
            check_cancelled()
            file = path / name
            require_unlinked(file)
            if not file.is_file():
                raise PackageCacheError()
            secure_path(file) if secure else require_private(file)
            result[file.relative_to(directory).as_posix()] = file_sha256(file)
    return result


def _verified_entry(entry: Path, identity: str) -> Path:
    from .installation_bundle import _json_object
    try:
        require_private(entry)
        manifest = entry / 'manifest.json'
        require_private(manifest)
        saved = _json_object(manifest)
        if (set(path.name for path in entry.iterdir()) != {'manifest.json', 'data'} or
                saved.get('version') != 1 or saved.get('identity') != identity or
                saved.get('files') != _inventory(entry / 'data')):
            raise PackageCacheError()
        check_cancelled()
    except OperationCancelled:
        raise
    except (OSError, LauncherError):
        raise PackageCacheError() from None
    return entry / 'data'


def _copy_acquisition(candidate: Path, destination: Path, kind: str) -> None:
    # npm diagnostics/configuration may contain private source or proxy details;
    # only its content-addressed cache is reusable. npm itself needs URL-keyed
    # entries in that cache, so keep those internal package metadata intact.
    source = candidate / '_cacache' if kind == 'npm' else candidate
    require_unlinked(source)
    if not source.is_dir():
        raise PackageCacheError()
    for current, directories, files in os.walk(source, followlinks=False):
        check_cancelled()
        for name in (*directories, *files):
            require_unlinked(Path(current) / name)
        for name in files:
            if not (Path(current) / name).is_file():
                raise PackageCacheError()
    if kind == 'npm':
        destination.mkdir()
        destination = destination / '_cacache'
    shutil.copytree(source, destination)


def acquire_cached(cache_root: Path | None, *, kind: str, locks: tuple[Path, ...], target,
                   mode: str, source: str, candidate: Path, acquire, report) -> Path | None:
    """Publish only successful, complete acquisitions; never mutate a warm entry.

    A source-mode/origin-specific key prevents an unapproved registry or an
    online cache from becoming an implicit offline source. Full lock hashes and
    the actual target runtime bind platform/marker-dependent package choices.
    The callback returns False only for a permitted source availability failure.
    """
    if cache_root is None:
        return candidate if acquire() else None
    lock_hashes = [file_sha256(path) for path in locks]
    identity = hashlib.sha256(json.dumps({
        'version': 1, 'kind': kind, 'locks': lock_hashes,
        'target': target, 'mode': mode, 'source': source,
    }, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    # Persist only the digest, never source URLs, commands or captured output.
    root = private_directory(Path(cache_root))
    # The locator stays short for npm's 124-character content-addressed leaves
    # on Windows without LongPathsEnabled. Full identity remains authoritative;
    # an unlikely prefix collision is rejected, never silently shared.
    locator = identity[:12]
    with resource_locks(root, {'package:' + kind + ':' + locator: True}):
        entries = private_directory(root / kind, root=root)
        entry = entries / locator
        require_unlinked(entry)
        check_cancelled()
        if entry.exists():
            data = _verified_entry(entry, identity)
            report('Paket edinimi doğrulandı; kalıcı önbellek kullanılıyor')
            return data
        if not acquire():
            return None
        check_cancelled()
        if [file_sha256(path) for path in locks] != lock_hashes:
            raise PackageCacheError()
        with tempfile.TemporaryDirectory(prefix='.p-', dir=entries) as temporary:
            pending = Path(temporary)
            secure_path(pending)
            _copy_acquisition(candidate, pending / 'data', kind)
            files = _inventory(pending / 'data', secure=True)
            manifest = pending / 'manifest.json'
            manifest.write_text(json.dumps({'version': 1, 'identity': identity, 'files': files},
                                           sort_keys=True), encoding='utf-8')
            secure_path(manifest)
            check_cancelled()
            os.replace(pending, entry)
        return entry / 'data'
