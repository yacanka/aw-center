"""Cached, parallel, circuit-broken Integration Hub probe orchestration."""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from awcenter.integration_probe_adapters import ProbeOutcome, probe_integration

CACHE_PREFIX = "aw:integration-probe:v1"
FAILURE_STATUSES = {"degraded", "unavailable"}


def probe_catalog(catalog: list[dict], refresh: bool = False) -> list[dict]:
    """Attach parallel live-health observations to catalog entries."""

    identifiers = [item["id"] for item in catalog]
    worker_count = min(len(identifiers), settings.INTEGRATION_PROBE_MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=max(1, worker_count)) as executor:
        results = executor.map(lambda identifier: _get_probe(identifier, refresh), identifiers)
    health_by_identifier = dict(zip(identifiers, results, strict=True))
    return [{**item, "health": health_by_identifier[item["id"]]} for item in catalog]


def claim_refresh_slot(subject_identifier: object) -> bool:
    """Rate-limit forced refreshes per authenticated subject."""

    key = f"{CACHE_PREFIX}:refresh:{subject_identifier}"
    timeout = max(1, settings.INTEGRATION_PROBE_REFRESH_COOLDOWN_SECONDS)
    return cache.add(key, True, timeout=timeout)


def _get_probe(identifier: str, refresh: bool) -> dict:
    cached = None if refresh else cache.get(_key(identifier, "result"))
    if cached:
        return {**cached, "source": "cache"}
    if cache.get(_key(identifier, "circuit")):
        return _circuit_result()
    if not cache.add(_key(identifier, "lock"), True, timeout=_lock_seconds()):
        concurrent_result = cache.get(_key(identifier, "result"))
        if concurrent_result:
            return {**concurrent_result, "source": "cache"}
        return _busy_result()
    try:
        return _run_probe(identifier)
    finally:
        cache.delete(_key(identifier, "lock"))


def _run_probe(identifier: str) -> dict:
    started_at = monotonic()
    try:
        outcome = probe_integration(identifier)
    except Exception:
        outcome = ProbeOutcome("unavailable", "The live health check failed safely.")
    result = _serialize(outcome, started_at)
    cache.set(_key(identifier, "result"), result, timeout=_cache_seconds())
    _record_circuit_state(identifier, outcome.status)
    return result


def _serialize(outcome: ProbeOutcome, started_at: float) -> dict:
    return {
        "status": outcome.status,
        "detail": outcome.detail,
        "checked_at": timezone.now().isoformat(),
        "latency_ms": max(0, round((monotonic() - started_at) * 1000)),
        "source": "live",
    }


def _record_circuit_state(identifier: str, status: str) -> None:
    failure_key = _key(identifier, "failures")
    if status not in FAILURE_STATUSES:
        cache.delete_many([failure_key, _key(identifier, "circuit")])
        return
    cache.add(failure_key, 0, timeout=settings.INTEGRATION_PROBE_FAILURE_WINDOW_SECONDS)
    failures = cache.incr(failure_key)
    if failures >= settings.INTEGRATION_PROBE_FAILURE_THRESHOLD:
        cache.set(
            _key(identifier, "circuit"),
            True,
            timeout=settings.INTEGRATION_PROBE_CIRCUIT_COOLDOWN_SECONDS,
        )


def _circuit_result() -> dict:
    return {
        "status": "unavailable",
        "detail": "Live checks are temporarily paused after repeated failures.",
        "checked_at": timezone.now().isoformat(),
        "latency_ms": 0,
        "source": "circuit",
    }


def _busy_result() -> dict:
    return {
        "status": "checking",
        "detail": "Another worker is refreshing this integration.",
        "checked_at": None,
        "latency_ms": None,
        "source": "busy",
    }


def _key(identifier: str, suffix: str) -> str:
    return f"{CACHE_PREFIX}:{identifier}:{suffix}"


def _cache_seconds() -> int:
    return settings.INTEGRATION_PROBE_CACHE_SECONDS


def _lock_seconds() -> int:
    return max(5, int(settings.INTEGRATION_PROBE_READ_TIMEOUT_SECONDS) + 2)
