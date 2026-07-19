"""Lightweight media signature checks used before FFmpeg receives uploads."""

MEDIA_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".avi", ".mp3", ".wav"})


def matches_media_signature(extension: str, header: bytes) -> bool:
    """Return whether leading bytes match a supported media container."""

    if extension in {".mp4", ".mov"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if extension in {".webm", ".mkv"}:
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if extension == ".avi":
        return header.startswith(b"RIFF") and header[8:12] == b"AVI "
    if extension == ".wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if extension == ".mp3":
        return header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}
    return False
