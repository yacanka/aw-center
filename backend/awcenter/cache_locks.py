"""Bounded process-shared locks for security-sensitive file-cache operations."""

import hashlib
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep

from django.conf import settings
from django.core.cache import cache, caches
from django.core.cache.backends.filebased import FileBasedCache
from django.core.files import locks

logger = logging.getLogger(__name__)
LOCK_TIMEOUT_SECONDS = 2


@contextmanager
def cache_entry_lock(key):
    """Serialize file-cache operations; yield False if the lock is unavailable."""

    if not isinstance(caches["default"], FileBasedCache):
        yield True
        return
    try:
        lock_file = _open_locked_file(key)
    except OSError:
        lock_file = None
    if lock_file is None:
        logger.warning("File cache operation lock unavailable.")
        yield False
        return
    try:
        yield True
    finally:
        try:
            locks.unlock(lock_file)
        finally:
            lock_file.close()


def atomic_cache_add(key, value, timeout):
    """Add a cache entry once, including on Django's non-atomic file backend."""

    with cache_entry_lock(key) as acquired:
        return bool(acquired and cache.add(key, value, timeout=timeout))


def _open_locked_file(key):
    # Fixed lock stripes bound file count and keep lock names free of capabilities.
    # Keep these files: unlinking a live lock could let processes lock different inodes.
    directory = Path(settings.CACHES["default"]["LOCATION"]) / ".operation-locks"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stripe = hashlib.sha256(key.encode("utf-8")).hexdigest()[:2]
    descriptor = os.open(directory / f"{stripe}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    lock_file = os.fdopen(descriptor, "r+b")
    try:
        if _acquire_lock(lock_file):
            return lock_file
    except BaseException:
        lock_file.close()
        raise
    lock_file.close()
    return None


def _acquire_lock(lock_file):
    deadline = monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        if locks.lock(lock_file, locks.LOCK_EX | locks.LOCK_NB):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        sleep(min(0.01, remaining))
