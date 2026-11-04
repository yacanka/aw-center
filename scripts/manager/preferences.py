"""Bounded, owner-only persistence for non-secret desktop form inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from scripts.launcher.installation_permissions import require_private, require_unlinked, secure_path
from scripts.launcher.installation_state import private_directory
from scripts.launcher.model import LauncherError
from .view_model import DEFAULT_VALUES, FormError, _https

_LIMIT = 128 * 1024


def _safe_values(values: dict) -> dict:
    result = {}
    for key, default in DEFAULT_VALUES.items():
        value = values.get(key)
        # Migration authorization is specific to one operation, never a preference.
        if key == 'migrate' or type(value) is not type(default):
            continue
        if isinstance(value, str):
            value = value.strip()
            if len(value) > 8192 or any(character in value for character in '\0\r\n'):
                continue
            if value and (key in {'python_index_url', 'npm_registry_url'} or
                          (key == 'repository' and '://' in value)):
                try:
                    _https(value, key)
                except FormError:
                    continue
        if key == 'profile' and value not in {'dev', 'prod'}:
            continue
        if key == 'source_mode' and value not in {'online', 'corporate', 'offline'}:
            continue
        result[key] = value
    return result


def load_preferences(home: Path) -> dict:
    """Read settings without creating profiles or interpreting any saved command."""
    path = home / 'config/manager.json'
    require_unlinked(path)
    if not path.exists():
        return {}
    for item in (home, path.parent, path):
        require_private(item)
    try:
        with path.open('rb') as stream:
            content = stream.read(_LIMIT + 1)
        if len(content) > _LIMIT:
            raise ValueError
        document = json.loads(content)
        if (not isinstance(document, dict) or document.get('version') != 1 or
                not isinstance(document.get('values'), dict)):
            raise ValueError
        return _safe_values(document['values'])
    except (ValueError, UnicodeError, RecursionError):
        raise LauncherError('Kayıtlı Manager form ayarları geçersiz.') from None


def save_preferences(home: Path, values: dict) -> None:
    """Atomically replace only supported inputs; never read selected file contents."""
    content = json.dumps({'version': 1, 'values': _safe_values(values)}, ensure_ascii=False).encode('utf-8')
    if len(content) > _LIMIT:
        raise LauncherError('Manager form ayarları boyut sınırını aştı.')
    private_directory(home)
    directory = private_directory(home / 'config')
    destination = directory / 'manager.json'
    require_unlinked(destination)
    if destination.exists():
        require_private(destination)
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix='.manager-')
    path = Path(temporary)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            secure_path(path)
            stream.write(content)
        os.replace(path, destination)
    finally:
        path.unlink(missing_ok=True)
