"""Scheduling helpers for real file-cache capability concurrency tests."""

from contextlib import contextmanager
from threading import local
from unittest.mock import patch


@contextmanager
def synchronized_file_cache_reads(key, read_barrier, add_barrier):
    from django.core.cache.backends.filebased import FileBasedCache

    original_get = FileBasedCache.get
    original_has_key = FileBasedCache.has_key
    reads = local()

    def synchronized_get(backend, requested_key, *args, **kwargs):
        package = original_get(backend, requested_key, *args, **kwargs)
        if requested_key == key and not getattr(reads, "synchronized", False):
            reads.synchronized = True
            read_barrier.wait(timeout=10)
        return package

    def synchronized_has_key(backend, requested_key, *args, **kwargs):
        present = original_has_key(backend, requested_key, *args, **kwargs)
        if requested_key == f"{key}:consumed":
            add_barrier.wait(timeout=10)
        return present

    # Run real I/O; pause initial reads only, outside the consumption lock, and the
    # former non-atomic add fence. Keeping imports local makes spawn safe.
    with (
        patch.object(FileBasedCache, "get", synchronized_get),
        patch.object(FileBasedCache, "has_key", synchronized_has_key),
    ):
        yield


def consume_file_cache_in_process(directory, capability, owner_id, read_barrier, add_barrier, results):
    import django

    django.setup()
    from django.test import override_settings
    from outlook.views import cache_key, consume_attachment_capability

    with (
        override_settings(CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
                "LOCATION": directory,
            },
        }),
        synchronized_file_cache_reads(cache_key(capability), read_barrier, add_barrier),
    ):
        results.put(consume_attachment_capability(capability, owner_id) is not None)
