#!/usr/bin/env python3
"""Isolation: dual-peak P0 — no red half-trim + episode lock (2026-08-26)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_lifecycle import DEFAULTS_P2, evaluate_dual_peak_exits


def _dist_candles(n: int = 40, last_off: float = 0.05):
    """Synthetic daily path that lands in late/distribution-ish highs then soft."""
    rows = []
    t0 = 1_700_000_000
    px = 100.0
    for i in range(n):
        # climb then fail high
        if i < n - 5:
            h = px * 1.02
            c = px * 1.01
            l = px * 0.99
            o = px
            px = c
        else:
            h = px * (1.0 - last_off * 0.2)
            c = px * (1.0 - last_off)
            l = c * 0.99
            o = px
            px = c
        rows.append([t0 + i * 86400, o, h, l, c, 1000.0])
    return rows


def main() -> int:
    fails = []
    cfg = copy.deepcopy(DEFAULTS_P2)
    cfg["mode"] = "live"
    # force price_hit via distribution-like path; we also set phase via candles
    candles = _dist_candles()

    base_lot = {
        "pair": "BTC-USD",
        "open": True,
        "entry_price": 100.0,
        "entry_sentiment": 0.80,
        "entry_sent_peak": 0.80,
        "peak_price": 110.0,  # +10% MFE sticky
        "usd": 500.0,
    }

    # 1) RED mark → no dual_peak, no extension_partial
    red = evaluate_dual_peak_exits(
        lots=[base_lot],
        current_sentiment={"BTC-USD": 0.05},
        current_prices={"BTC-USD": 98.0},  # red vs entry
        positions_usd={"BTC-USD": 500.0},
        candles_by_pair={"BTC-USD": candles},
        cfg_p2=cfg,
    )
    if red:
        fails.append(f"red mark must emit no lifecycle trim, got {[(e.kind, e.reasons) for e in red]}")
    else:
        print("no_red_trim OK")

    # 2) GREEN + fade + off peak → dual_peak allowed once
    green = evaluate_dual_peak_exits(
        lots=[base_lot],
        current_sentiment={"BTC-USD": 0.05},
        current_prices={"BTC-USD": 104.0},  # green vs entry, off peak from 110
        positions_usd={"BTC-USD": 500.0},
        candles_by_pair={"BTC-USD": candles},
        cfg_p2=cfg,
    )
    kinds = {e.kind for e in green}
    if "dual_peak" not in kinds and "extension_partial" not in kinds:
        fails.append(f"green faded bag should emit dual or extension, got {green}")
    else:
        print("green_emit OK", [(e.kind, e.would_trim_frac) for e in green])

    # 3) Episode lock after dual_peak_trim_count >= 1 (no new peak)
    spent = dict(base_lot)
    spent["dual_peak_trim_count"] = 1
    spent["peak_at_last_dual_peak"] = 110.0
    locked = evaluate_dual_peak_exits(
        lots=[spent],
        current_sentiment={"BTC-USD": 0.05},
        current_prices={"BTC-USD": 104.0},
        positions_usd={"BTC-USD": 500.0},
        candles_by_pair={"BTC-USD": candles},
        cfg_p2=cfg,
    )
    dual_locked = [e for e in locked if e.kind == "dual_peak"]
    if dual_locked:
        fails.append(f"episode lock failed, still dual_peak: {dual_locked}")
    else:
        print("episode_lock OK")

    # 4) Rearm when peak rises above peak_at_last_dual_peak
    rearm = dict(spent)
    rearm["peak_price"] = 120.0  # clear new peak vs 110 lock
    rearmed = evaluate_dual_peak_exits(
        lots=[rearm],
        current_sentiment={"BTC-USD": 0.05},
        # green vs entry 100, ≥3% off new peak 120 → failed_high
        current_prices={"BTC-USD": 112.0},
        positions_usd={"BTC-USD": 500.0},
        candles_by_pair={"BTC-USD": candles},
        cfg_p2=cfg,
    )
    dual_re = [e for e in rearmed if e.kind == "dual_peak"]
    if not dual_re:
        fails.append(f"rearm on new peak expected dual_peak, got {[(e.kind, e.reasons) for e in rearmed]}")
    else:
        print("rearm_path OK", dual_re[0].reasons)

    # 5) Legacy last_trim_kind=dual_peak without count → locked
    legacy = dict(base_lot)
    legacy["last_trim_kind"] = "dual_peak"
    leg = evaluate_dual_peak_exits(
        lots=[legacy],
        current_sentiment={"BTC-USD": 0.05},
        current_prices={"BTC-USD": 104.0},
        positions_usd={"BTC-USD": 500.0},
        candles_by_pair={"BTC-USD": candles},
        cfg_p2=cfg,
    )
    if any(e.kind == "dual_peak" for e in leg):
        fails.append(f"legacy last_trim dual_peak must lock dual, got {leg}")
    else:
        print("legacy_lock OK")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
