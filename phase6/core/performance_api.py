# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
Temporary Performance API + Cache (Dashboard)
Easy cache flushing support.
"""

import time
from typing import Any, Dict, Optional


class PerformanceCache:
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        if time.time() - self._timestamps[key] > self.ttl:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            return None
        return self._cache[key]

    def set(self, key: str, value: Any):
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def flush(self):
        self._cache.clear()
        self._timestamps.clear()

    def flush_key(self, key: str):
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)


performance_cache = PerformanceCache(ttl_seconds=300)


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
