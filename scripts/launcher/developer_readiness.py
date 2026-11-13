"""Small developer-only package hints, never comprehensive integrity evidence.

The full package receipt remains authoritative for completed installation. A hint
only avoids repeatedly parsing its large file map; it cannot authorize managed
startup, and is invalidated by a different receipt or lock identity.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import json
import tempfile

from .installation_bundle import _json_object
from .installation_permissions import require_unlinked
from .model import LauncherError
from .offline_manifest import file_sha256


def _receipt_identity(path: Path) -> list[int]:
    require_unlinked(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
        raise ValueError('invalid package receipt')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def _publish(path: Path, document: dict) -> None:
    require_unlinked(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        require_unlinked(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def stage_current(project, name: str, target: Path, lock: Path | None,
                  receipt: Path, *, required: tuple[Path, ...]) -> bool:
    """Check a completed stage and required outputs without walking its tree."""
    require_unlinked(receipt)
    if not receipt.is_file() or lock is None:
        return False
    require_unlinked(lock)
    if not lock.is_file():
        return False
    for path in required:
        require_unlinked(path)
        if not path.is_file():
            return False
    identity = _receipt_identity(receipt)
    lock_digest = file_sha256(lock)
    context = {'version': 1, 'source': str(project.root.absolute()),
               'target': str(target.absolute()), 'lock_path': str(lock.absolute()),
               'receipt': identity}
    cache = project.root / '.runtime' / 'developer-readiness' / (name + '.json')
    require_unlinked(cache)
    try:
        saved = _json_object(cache, limit=16 * 1024)
        if (set(saved) == {*context, 'lock'} and
                all(saved.get(key) == value for key, value in context.items()) and
                isinstance(saved.get('lock'), str)):
            return saved['lock'] == lock_digest
    except (OSError, ValueError, LauncherError):
        # Malformed generated hints are disposable. Unsafe paths were rejected
        # above and never become writable cache destinations.
        pass
    saved = _json_object(receipt, limit=64 * 1024 * 1024)
    if (saved.get('version') != 1 or not isinstance(saved.get('files'), dict)
            or not isinstance(saved.get('lock'), str)):
        raise ValueError('invalid package receipt')
    if _receipt_identity(receipt) != identity:
        raise ValueError('package receipt changed during readiness check')
    _publish(cache, {**context, 'lock': saved['lock']})
    return saved['lock'] == lock_digest
