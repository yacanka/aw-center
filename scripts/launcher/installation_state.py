"""Private installation lock, runtime marker directory and sanitized reports."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .installation_permissions import require_private, require_unlinked, secure_path
from .model import LauncherError


def private_directory(path: Path) -> Path:
    require_unlinked(path)
    if path.exists():
        require_private(path)
    else:
        path.mkdir(parents=True)
        secure_path(path)
    return path


@contextmanager
def installation_lock(home: Path):
    """Use an OS-owned lock; a crashed process cannot leave a stale active lock."""
    private_directory(home)
    path = home / "installation.lock"
    require_unlinked(path)
    if path.exists():
        require_private(path)
    with path.open("a+b") as stream:
        secure_path(path)
        if path.stat().st_size == 0:
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


@contextmanager
def runtime_session(profile: dict):
    home = Path(profile["env_file"]).parent.parent
    parent = private_directory(home / "runs")
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
    directory = private_directory(home / "logs")
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
    directory = private_directory(home / "config")
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
