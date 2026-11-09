"""Private installation lock, runtime marker directory and sanitized reports."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .installation_permissions import (PermissionCheckError, prepare_private, require_local_ntfs,
                                       require_private, require_unlinked, secure_path)
from .model import LauncherError


def private_directory(path: Path, *, root: Path | None = None, progress=None) -> Path:
    """Secure every new ancestor and revalidate concurrent directory creation."""
    require_unlinked(path)
    if root is not None:
        require_unlinked(root)
        path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
        if not path.is_relative_to(root):
            raise PermissionCheckError('path_scope')
        if path != root:
            private_directory(path.parent, root=root, progress=progress)
    if not path.exists():
        if not path.parent.exists():
            private_directory(path.parent, progress=progress)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass  # Another creator must pass the same type/owner/ACL checks.
        else:
            secure_path(path)
    if not path.is_dir():
        raise PermissionCheckError('directory_type')
    if prepare_private(path) and progress is not None:
        progress('Kurulum klasörünün devralınan izinleri kullanıcıya özel olarak düzenlendi')
    return path


def prepare_installation_storage(home: Path, *, progress=None) -> None:
    """Admit explicit startup before reading profiles or doing expensive work.

    Only managed directory ACLs are prepared here. Existing profile/env/database
    files retain strict read checks; no content or ownership is repaired.
    """
    if progress is not None:
        progress('Kurulum alanı ve dosya yazma erişimi denetleniyor')
    require_local_ntfs(home)
    directories = [private_directory(home, root=home, progress=progress)]
    for name in ('config', 'locks'):
        path = home / name
        require_unlinked(path)
        if path.exists():
            private_directory(path, root=home, progress=progress)
            if name == 'config':
                directories.append(path)
    for directory in directories:
        if progress is not None:
            progress('Kurulum alanının yazma ve atomik dosya değiştirme erişimi denetleniyor')
        _probe_writable(directory)


def _probe_writable(directory: Path) -> None:
    """Exercise real create/fsync/replace access without touching existing state."""
    with tempfile.TemporaryDirectory(prefix='.startup-check-', dir=directory) as temporary:
        scratch = Path(temporary)
        secure_path(scratch)
        source, destination = scratch / 'source', scratch / 'destination'
        with source.open('xb') as stream:
            secure_path(source)
            stream.write(b'0')
            stream.flush()
            os.fsync(stream.fileno())
        destination.touch(exist_ok=False)
        os.replace(source, destination)


@contextmanager
def installation_lock(home: Path):
    """Use an OS-owned lock; a crashed process cannot leave a stale active lock."""
    private_directory(home, root=home)
    path = home / "installation.lock"
    with open_private_lock(path) as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise LauncherError("Başka bir AW Center kurulumu devam ediyor.") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def open_private_lock(path: Path):
    """Secure a proven new lock or prepare an existing one without owner writes."""
    require_unlinked(path)
    try:
        stream = path.open('x+b')
        created = True
    except FileExistsError:
        stream = path.open('r+b')
        created = False
    try:
        if created:
            secure_path(path, file_descriptor=stream.fileno())
        else:
            prepare_private(path, file_descriptor=stream.fileno())
    except BaseException:
        stream.close()
        raise
    return stream


@contextmanager
def runtime_session(profile: dict):
    home = Path(profile["env_file"]).parent.parent
    parent = private_directory(home / "runs", root=home)
    with tempfile.TemporaryDirectory(prefix=profile["name"] + "-", dir=parent) as temporary:
        directory = Path(temporary)
        secure_path(directory)
        yield directory


@contextmanager
def process_environment(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def save_report(home: Path, profile: str, checks: list[dict]) -> None:
    """Persist only declared result fields, never child output or configuration."""
    directory = private_directory(home / "logs", root=home)
    destination = directory / f"installation-{profile}.json"
    require_unlinked(destination)
    if destination.exists():
        require_private(destination)
    content = {"time": datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M:%S"),
               "profile": profile, "checks": checks}
    encoded = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > 128 * 1024:
        raise LauncherError("Kurulum raporu boyut sınırını aştı.")
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".report-")
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            secure_path(path)
            output.write(encoded)
        os.replace(path, destination)
    finally:
        path.unlink(missing_ok=True)


def load_sources(home: Path) -> dict:
    """Read only non-secret source preferences; credentials never belong here."""
    path = home / "config" / "sources.json"
    require_unlinked(path)
    if not path.exists():
        return {}
    require_private(path.parent)
    require_private(path)
    try:
        if path.stat().st_size > 16 * 1024:
            raise ValueError
        content = json.loads(path.read_text(encoding="utf-8"))
        allowed = {"repository", "offline_dir", "python_index_url", "npm_registry_url", "ca_file", "mode"}
        if not isinstance(content, dict) or set(content) - allowed:
            raise ValueError
        if any(not isinstance(value, str) or any(char in value for char in "\r\n\0") for value in content.values()):
            raise ValueError
        if content.get("mode", "online") not in {"online", "restricted", "corporate", "offline"}:
            raise ValueError
        return content
    except (ValueError, UnicodeError):
        raise LauncherError("Kayıtlı paket kaynakları geçersiz; kaynak dosyasını kontrol edin.") from None


def save_sources(home: Path, settings) -> None:
    directory = private_directory(home / "config", root=home)
    destination = directory / "sources.json"
    require_unlinked(destination)
    if destination.exists():
        require_private(destination)
    fields = ("repository", "offline_dir", "python_index_url", "npm_registry_url", "ca_file", "mode")
    content = {key: str(getattr(settings, key)) for key in fields if getattr(settings, key, None)}
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".sources-")
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            secure_path(path)
            json.dump(content, output)
            output.write("\n")
        os.replace(path, destination)
    finally:
        path.unlink(missing_ok=True)
