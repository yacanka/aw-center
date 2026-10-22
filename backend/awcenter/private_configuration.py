"""Bounded, read-only JSON files outside the source checkout."""

import json
import os
from pathlib import Path
import stat

from django.conf import settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAX_CONFIGURATION_BYTES = 64 * 1024


class PrivateConfigurationError(ValueError):
    """Never expose the configured path, data or parser exception."""


def read_private_json(setting_name):
    """Read an explicit external file; POSIX requires current owner and mode 0600.

    Windows operators must verify the file and parent NTFS ACLs separately.
    Duplicate keys and unsupported schema versions are rejected.
    """
    try:
        raw = _read_bytes(getattr(settings, setting_name, ""))
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
            raise ValueError
        if value["schema_version"] != 1:
            raise ValueError
        return value
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        raise PrivateConfigurationError("Private workflow configuration is unavailable or invalid.") from None


def _read_bytes(configured):
    path = Path(configured).expanduser()
    if not configured or not path.is_absolute():
        raise ValueError
    path = path.resolve(strict=True)
    if path.is_relative_to(REPOSITORY_ROOT) or not path.is_file():
        raise ValueError
    with path.open("rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIGURATION_BYTES:
            raise ValueError
        if os.name == "posix" and (
            metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError
        raw = stream.read(MAX_CONFIGURATION_BYTES + 1)
    if len(raw) > MAX_CONFIGURATION_BYTES:
        raise ValueError
    return raw


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result
