#!/usr/bin/env python3
"""P1: mover ∩ not-in-bag watchlist (no bag mutation)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.market_posture_explain import refresh_mover_not_in_bag_watchlist


def main() -> int:
    out = refresh_mover_not_in_bag_watchlist(force_heat=True)
    print(
        json.dumps(
            {
                "ok": True,
                "n": out.get("n"),
                "heat_hot": out.get("heat_hot"),
                "btc_24h": out.get("btc_change_24h_pct"),
                "top": [r.get("pair") for r in (out.get("watchlist") or [])[:8]],
                "path": "data/state/mover_not_in_bag_watchlist.json",
                "report": out.get("report"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
