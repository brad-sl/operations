#!/usr/bin/env python3
"""Refresh BTC-30d / regime watch for bull defensive-rotation shadow readiness."""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

ACT = ROOT / "scripts/phase6/activate_bull_defensive_rotation_shadow.py"


def main() -> int:
    # Load sibling module without package import
    ns = runpy.run_path(str(ACT))
    ready = json.loads(ns["READY"].read_text())
    ok, failures, ctx = ns["evaluate_gates"](ready)
    ns["write_watch"](ctx)
    live = ctx.get("live") or {}
    btc = live.get("btc_return_pct_live")
    if btc is None:
        btc = live.get("btc_return_pct")
    regime = live.get("regime_live") or live.get("regime")
    print(
        f"bull_reentry_watch regime={regime} btc_30d={btc} "
        f"gates_ok={ok} fails={failures or 'none'}"
    )
    print("wrote data/state/bull_reentry_watch.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
