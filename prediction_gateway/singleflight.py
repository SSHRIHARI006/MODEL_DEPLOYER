from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Any
from django.core.cache import cache

logger = logging.getLogger(__name__)

# In-memory thread lock registry fallback when Redis is absent
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_REGISTRY_LOCK = threading.Lock()


def _get_local_lock(key: str) -> threading.Lock:
    with _LOCAL_REGISTRY_LOCK:
        if key not in _LOCAL_LOCKS:
            _LOCAL_LOCKS[key] = threading.Lock()
        return _LOCAL_LOCKS[key]


class SingleFlight:
    """PERF-02: Prevents duplicate concurrent cold-cache inference for identical payloads.

    Concurrent requests for the exact same model version + input payload coordinate so
    only one request calls the runner (the leader), while concurrent waiters poll the
    cache for a bounded deadline. If the leader finishes, waiters receive the cached
    result. If the leader fails or times out, waiters fall back to direct execution.
    """

    def __init__(self, lock_timeout_sec: float = 15.0, poll_interval_sec: float = 0.05):
        self.lock_timeout_sec = lock_timeout_sec
        self.poll_interval_sec = poll_interval_sec

    def execute(
        self,
        cache_key: str,
        execute_fn: Callable[[], Any],
        get_cache_fn: Callable[[str], Any],
    ) -> tuple[Any, bool]:
        """Executes execute_fn with single-flight suppression.

        Returns (result, was_cached).
        """
        # 1. First check cache
        cached = get_cache_fn(cache_key)
        if cached is not None:
            return cached, True

        flight_lock_key = f"flight:{cache_key}"
        lock = _get_local_lock(flight_lock_key)

        acquired = lock.acquire(blocking=False)
        if acquired:
            try:
                # Double-check cache after acquiring lock
                cached = get_cache_fn(cache_key)
                if cached is not None:
                    return cached, True

                # We are the leader: execute the underlying function
                result = execute_fn()
                return result, False
            finally:
                lock.release()
        else:
            # We are a waiter: wait bounded time for leader to populate cache
            deadline = time.time() + self.lock_timeout_sec
            while time.time() < deadline:
                time.sleep(self.poll_interval_sec)
                cached = get_cache_fn(cache_key)
                if cached is not None:
                    return cached, True
                # If leader finished and released lock without caching (e.g. failure), break out
                if lock.acquire(blocking=False):
                    lock.release()
                    break

            # Fallback if leader failed or timed out: execute directly
            result = execute_fn()
            return result, False


single_flight = SingleFlight()
