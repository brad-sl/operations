#!/usr/bin/env python3
"""Fetch live quotes for all Phase 6 pairs into data/state/price_history.json (runner uses same path)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.paths import PRICE_HISTORY
from phase6.core.price_history_manager import PriceHistoryManager

FIXED_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD",
]


def main() -> int:
    ex = CoinbaseExchangeClient(mode="live")
    mgr = PriceHistoryManager(persist_path=str(PRICE_HISTORY))
    updated = 0
    for pair in FIXED_UNIVERSE:
        px = float(ex.get_price(pair) or 0)
        if px > 0:
            mgr.add_price(pair, px)
            updated += 1
            print(f"{pair} {px}")
    mgr.flush()
    print(f"[OK] {updated} quotes -> {PRICE_HISTORY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())