"""Data-only configuration shared by the Windows dashboard packager, API and reader."""

import re
import struct
import unicodedata
from pathlib import Path, PureWindowsPath
from typing import BinaryIO


_TEMPLATE = b"\0AWCENTER:CertificationDashboard:template:v1\0"
_CONFIG = b"\0AWCENTER:CertificationDashboard:config:v1\0"
_COOKIE_MAGIC = b"MEI\014\013\012\013\016"
_COOKIE = struct.Struct("!8sIIII64s")
_MAX_PATH_BYTES = 4096 - len(_TEMPLATE) - len(_CONFIG) - 3
_INVALID_PATH = "Yerel bir sürücüde veya ağ paylaşımında .sqlite3, .sqlite veya .db dosyasının tam yolunu girin."
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[0-9¹²³])", re.I)
_HOST = re.compile(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*")


def _valid_segment(segment: str) -> bool:
    return (
        bool(segment) and not segment.endswith((".", " "))
        and not _RESERVED.fullmatch(segment.split(".", 1)[0].rstrip(" "))
        and not any(ch in '<>:"/|?*' or unicodedata.category(ch).startswith("C") for ch in segment)
        and len(segment.encode("utf-16-le")) <= 510
    )


def validate_database_path(value: str) -> str:
    """Validate Windows path syntax only. Never resolve, stat or open the supplied path."""
    if not isinstance(value, str) or not value or len(value) > _MAX_PATH_BYTES:
        raise ValueError(_INVALID_PATH)
    path = value.replace("/", "\\")
    if path.startswith("\\\\"):
        parts = path[2:].split("\\")
        if (len(parts) < 3 or not _HOST.fullmatch(parts[0])
                or parts[1].lower() in {"davwwwroot", "pipe", "mailslot", "ipc$"}):
            raise ValueError(_INVALID_PATH)
    elif re.match(r"^[A-Za-z]:\\", path):
        parts = path[3:].split("\\")
    else:
        raise ValueError(_INVALID_PATH)
    if not all(_valid_segment(part) for part in parts) or len(path.encode("utf-8")) > _MAX_PATH_BYTES:
        raise ValueError(_INVALID_PATH)
    if PureWindowsPath(path).suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError(_INVALID_PATH)
    return path


def permitted_share(path: str, roots: tuple[str, ...]) -> bool:
    """Compare a validated UNC path to complete configured server/share components."""
    # DNS host is ASCII. Preserve the administrator's literal Unicode share name
    # instead of conflating distinct names through Unicode casefold expansion.
    server, share, *_ = path[2:].split("\\")
    requested = f"\\\\{server.lower()}\\{share.lower()}"
    return any(root.rstrip("\\").lower() == requested for root in roots)


def _check_template(stream: BinaryIO, marker_offset: int) -> None:
    """Check the PE header and the adjacent CPython 3.11 PyInstaller archive cookie."""
    if marker_offset < _COOKIE.size + 64:
        raise ValueError("Invalid dashboard template.")
    stream.seek(0)
    if stream.read(2) != b"MZ":
        raise ValueError("Invalid dashboard template.")
    stream.seek(60)
    pe_offset = int.from_bytes(stream.read(4), "little")
    if not 64 <= pe_offset < marker_offset - _COOKIE.size:
        raise ValueError("Invalid dashboard template.")
    stream.seek(pe_offset)
    if stream.read(4) != b"PE\0\0":
        raise ValueError("Invalid dashboard template.")
    stream.seek(marker_offset - _COOKIE.size)
    magic, size, toc, toc_size, version, _ = _COOKIE.unpack(stream.read(_COOKIE.size))
    if (magic != _COOKIE_MAGIC or version != 311 or size > marker_offset - pe_offset
            or not 0 < toc_size <= size - _COOKIE.size - toc):
        raise ValueError("Invalid dashboard template.")


def _has_marker(stream: BinaryIO, end: int) -> bool:
    if end < len(_TEMPLATE):
        return False
    stream.seek(end - len(_TEMPLATE))
    return stream.read(len(_TEMPLATE)) == _TEMPLATE


def mark_executable_template(executable: Path) -> None:
    """Stamp the trusted, unsigned onefile build once, before making it available to Django."""
    with executable.open("rb+") as stream:
        end = stream.seek(0, 2)
        marked = _has_marker(stream, end)
        _check_template(stream, end - len(_TEMPLATE) if marked else end)
        if not marked:
            stream.seek(end)
            stream.write(_TEMPLATE)


def template_size(stream: BinaryIO) -> int:
    """Verify the fixed build marker and return the length, rewinding for streaming."""
    end = stream.seek(0, 2)
    if not _has_marker(stream, end):
        raise ValueError("Invalid dashboard template.")
    _check_template(stream, end - len(_TEMPLATE))
    stream.seek(0)
    return end


def database_path_trailer(path: str, *, auto_open_network: bool = False) -> bytes:
    """Encode the validated path and the publisher's trusted-share decision."""
    payload = validate_database_path(path).encode("utf-8")
    return payload + len(payload).to_bytes(2, "big") + bytes([auto_open_network]) + _CONFIG


def embedded_configuration(executable: Path) -> tuple[str, bool]:
    """Read the locator and network auto-open decision, without opening the database."""
    with executable.open("rb") as stream:
        end = stream.seek(0, 2)
        if end < len(_CONFIG) + 3:
            raise ValueError("Missing dashboard configuration.")
        stream.seek(end - len(_CONFIG) - 3)
        length = int.from_bytes(stream.read(2), "big")
        flag = stream.read(1)
        path_offset = end - len(_CONFIG) - 3 - length
        if (stream.read(len(_CONFIG)) != _CONFIG or not 0 < length <= _MAX_PATH_BYTES
                or flag not in (bytes([0]), bytes([1]))):
            raise ValueError("Missing dashboard configuration.")
        if not _has_marker(stream, path_offset):
            raise ValueError("Invalid dashboard configuration.")
        _check_template(stream, path_offset - len(_TEMPLATE))
        stream.seek(path_offset)
        return validate_database_path(stream.read(length).decode("utf-8")), bool(flag[0])


def embedded_database_path(executable: Path) -> str:
    return embedded_configuration(executable)[0]
