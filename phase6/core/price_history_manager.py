#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

"""
PriceHistoryManager

Maintains a rolling price history per trading pair with optional persistence.
Designed for Phase 6 runner integration.

- In-memory buffer (default 100 prices)
- Optional JSON snapshot persistence
- Clean API for adding prices and retrieving history for RSI calculation
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class PriceHistoryManager:
    def __init__(self, max_history: int = 100, persist_path: Optional[str] = None):
        self.max_history = max_history
        self.persist_path = Path(persist_path) if persist_path else None
        self.history: Dict[str, List[float]] = {}
        self.last_updated: Dict[str, str] = {}

        if self.persist_path and self.persist_path.exists():
            self._load_from_disk()

    def _load_from_disk(self):
        try:
            data = json.loads(self.persist_path.read_text())
            self.history = data.get("history", {})
            self.last_updated = data.get("last_updated", {})
        except Exception as e:
            print(f"[PriceHistoryManager] Failed to load snapshot: {e}")

    def _save_to_disk(self):
        if not self.persist_path:
            return
        try:
            payload = {
                "history": self.history,
                "last_updated": self.last_updated,
                "saved_at": datetime.utcnow().isoformat()
            }
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_path.write_text(json.dumps(payload, indent=2))
        except Exception as e:
            print(f"[PriceHistoryManager] Failed to save snapshot: {e}")

    def add_price(self, pair: str, price: float):
        if pair not in self.history:
            self.history[pair] = []
        self.history[pair].append(float(price))

        # Trim to max_history
        if len(self.history[pair]) > self.max_history:
            self.history[pair] = self.history[pair][-self.max_history:]

        self.last_updated[pair] = datetime.utcnow().isoformat()

    def get_prices(self, pair: str, n: Optional[int] = None) -> List[float]:
        prices = self.history.get(pair, [])
        if n is None:
            return prices[:]
        return prices[-n:] if n > 0 else []

    def get_latest_price(self, pair: str) -> Optional[float]:
        prices = self.history.get(pair, [])
        return prices[-1] if prices else None

    def has_enough_data(self, pair: str, min_points: int = 15) -> bool:
        return len(self.history.get(pair, [])) >= min_points

    def flush(self):
        """Force persist current state to disk."""
        self._save_to_disk()

    def get_status(self) -> dict:
        return {
            "pairs_tracked": list(self.history.keys()),
            "counts": {p: len(self.history[p]) for p in self.history},
            "last_updated": self.last_updated
        }


# Quick self-test
if __name__ == "__main__":
    import tempfile
    import os

    print("=== PriceHistoryManager Self-Test ===")

    with tempfile.TemporaryDirectory() as tmp:
        persist_file = os.path.join(tmp, "price_history.json")

        mgr = PriceHistoryManager(max_history=50, persist_path=persist_file)

        # Add some prices
        for i in range(20):
            mgr.add_price("BTC-USD", 60000 + i * 10)
            mgr.add_price("ETH-USD", 3000 + i * 5)

        print("BTC prices:", mgr.get_prices("BTC-USD", 5))
        print("ETH latest:", mgr.get_latest_price("ETH-USD"))
        print("Has enough BTC data:", mgr.has_enough_data("BTC-USD", 15))

        # Persist
        mgr.flush()
        print("Snapshot saved to:", persist_file)

        # Reload
        mgr2 = PriceHistoryManager(max_history=50, persist_path=persist_file)
        print("Reloaded BTC count:", len(mgr2.get_prices("BTC-USD")))
        print("Status:", mgr2.get_status())

    print("=== Self-Test Complete ===")