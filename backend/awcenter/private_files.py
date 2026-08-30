"""Integrity helpers for authenticated files outside public media roots."""

import hashlib
import hmac


class PrivateFileIntegrityError(Exception):
    """Signal that a stored private artifact no longer matches its fingerprint."""


def open_verified_private_file(field_file, expected_sha256: str):
    """Open a private file only after streaming SHA-256 verification."""

    expected = str(expected_sha256 or "").lower()
    if len(expected) != 64:
        raise PrivateFileIntegrityError("Private file fingerprint is unavailable.")
    handle = field_file.open("rb")
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), expected):
            raise PrivateFileIntegrityError("Private file integrity verification failed.")
        handle.seek(0)
        return handle
    except Exception:
        handle.close()
        raise
