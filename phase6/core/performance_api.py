# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Temporary Performance API + Cache (Dashboard)
Easy cache flushing support.
"""

import threading
import time
from typing import Any, Dict, Optional


class PerformanceCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._ttls: Dict[str, float] = {}
        # Last *populated* payload survives short empty/timeout TTLs so UI never
        # flickers to all-null while a cold compute is in flight.
        self._last_good: Dict[str, Any] = {}
        self._last_good_ts: Dict[str, float] = {}
        self.ttl = ttl_seconds
        self.last_good_max_age = 900.0  # 15m hard ceiling
        self._lock = threading.Lock()

    @staticmethod
    def _is_populated(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        if any(value.get(k) is not None for k in ("today", "h24", "d7", "d14", "d30")):
            return True
        eq = value.get("equity_trend") or {}
        return eq.get("status") == "ok" and len(eq.get("points") or []) >= 2

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            ttl = self._ttls.get(key, self.ttl)
            if time.time() - self._timestamps[key] > ttl:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
                self._ttls.pop(key, None)
                return None
            return self._cache[key]

    def get_last_good(self, key: str, max_age: Optional[float] = None) -> Optional[Any]:
        """Return last populated payload even if fresh cache expired/empty."""
        with self._lock:
            if key not in self._last_good:
                return None
            age = time.time() - self._last_good_ts.get(key, 0.0)
            limit = self.last_good_max_age if max_age is None else float(max_age)
            if age > limit:
                return None
            return self._last_good[key]

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """Store value. Optional per-key ttl (seconds); default self.ttl."""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if ttl is None:
                self._ttls.pop(key, None)
            else:
                self._ttls[key] = float(ttl)
            if self._is_populated(value):
                self._last_good[key] = value
                self._last_good_ts[key] = time.time()

    def flush(self):
        """Drop fresh TTL entries. Keep last_good so concurrent polls do not flash N/A."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._ttls.clear()

    def flush_all(self):
        """Hard reset including last_good (tests / operator full wipe)."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._ttls.clear()
            self._last_good.clear()
            self._last_good_ts.clear()

    def flush_key(self, key: str):
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            self._ttls.pop(key, None)
            # Keep last_good for this key — same reason as flush().

    def expire_fresh(self, key: str) -> None:
        """Force fresh miss while retaining last_good (tests + controlled recompute)."""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            self._ttls.pop(key, None)


performance_cache = PerformanceCache(ttl_seconds=60)

# Single-flight: only one cold /api/performance DB compute at a time (prevents
# concurrent UI polls from stampeding a large SQLite and starving /api/balances).
perf_compute_lock = threading.Lock()
_perf_bg_started = False
_perf_bg_lock = threading.Lock()


def schedule_performance_recompute(worker) -> bool:
    """Start at most one background recompute. Returns True if started now."""
    global _perf_bg_started
    with _perf_bg_lock:
        if _perf_bg_started:
            return False
        _perf_bg_started = True

    def _run():
        global _perf_bg_started
        try:
            if not perf_compute_lock.acquire(blocking=False):
                return
            try:
                worker()
            finally:
                perf_compute_lock.release()
        finally:
            with _perf_bg_lock:
                _perf_bg_started = False

    threading.Thread(target=_run, name="perf-api-recompute", daemon=True).start()
    return True


def get_performance_summary(calc) -> Dict[str, Any]:
    cache_key = "performance_summary"
    cached = performance_cache.get(cache_key)
    if cached:
        return cached
    data = calc.get_all_periods()
    performance_cache.set(cache_key, data)
    return data


def flush_performance_cache():
    performance_cache.flush()
