"""Atomic per-user fixed-minute slots with fail-closed cache handling."""
import math
from time import time

from awcenter.cache_locks import atomic_cache_add
from integrations.ai import AIServiceError


def claim_request(user) -> int | None:
    """Claim one of ten slots; return remaining seconds when the bucket is full.

    Slot keys contain only the user ID, minute and index. Atomic cache add also
    handles the shared file-cache lock; unavailable lock claims count as occupied.
    Cache failures stop the provider call with a safe service-unavailable error.
    """
    now = time()
    bucket = math.floor(now / 60)
    wait = max(1, math.ceil((bucket + 1) * 60 - now))
    try:
        for slot in range(10):
            if atomic_cache_add(f"assistant:chat:{user.pk}:{bucket}:{slot}", True, timeout=wait):
                return None
    except Exception:
        raise AIServiceError("The AI service is unavailable.", "AI_UNAVAILABLE", 503) from None
    return wait
