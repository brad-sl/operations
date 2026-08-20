#!/usr/bin/env python3
"""One-shot bear profit-take shadow cycle (no orders)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from phase6.core.bear_profit_take_shadow import apply_bear_profit_take_from_runner

    r = apply_bear_profit_take_from_runner(None)
    print(json.dumps(
        {
            "status": r.get("status"),
            "regime": r.get("regime"),
            "mode": r.get("mode"),
            "orders_placed": r.get("orders_placed"),
            "n_new_episodes": r.get("n_new_episodes"),
            "n_signals": r.get("n_signals"),
            "plain_english": r.get("plain_english"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
