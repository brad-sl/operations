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
        self.ttl = ttl_seconds
        self._lock = threading.Lock()

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

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """Store value. Optional per-key ttl (seconds); default self.ttl."""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if ttl is None:
                self._ttls.pop(key, None)
            else:
                self._ttls[key] = float(ttl)

    def flush(self):
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._ttls.clear()

    def flush_key(self, key: str):
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            self._ttls.pop(key, None)


performance_cache = PerformanceCache(ttl_seconds=60)

# Single-flight: only one cold /api/performance DB compute at a time (prevents
# concurrent UI polls from stampeding a large SQLite and starving /api/balances).
perf_compute_lock = threading.Lock()


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
