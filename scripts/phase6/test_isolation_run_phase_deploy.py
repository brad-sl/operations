#!/usr/bin/env python3
"""
Isolation tests: run-phase deploy gate (P0).

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/test_isolation_run_phase_deploy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_phase_deploy import (
    PHASE_DISTRIBUTION,
    PHASE_EXHAUSTION,
    PHASE_EXTENSION,
    PHASE_IGNITION,
    PHASE_TREND,
    apply_run_phase_buy_gate,
    apply_run_phase_to_actions,
    classify_run_phase,
    fetch_daily_candles_public,
    load_run_phase_config,
)


def _mk_candles(closes, vols=None, start_t=1_700_000_000):
    """Synthetic daily candles from closes (flat OHLC)."""
    rows = []
    for i, c in enumerate(closes):
        v = (vols[i] if vols else 1000.0)
        # mild wick
        rows.append(
            [
                start_t + i * 86400,
                c * 0.99,
                c * 1.01,
                c * 0.995,
                c,
                v,
            ]
        )
    return rows


def main() -> int:
    fails = []
    cfg = load_run_phase_config(
        json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    )
    assert cfg.get("enabled") is True

    # --- Synthetic ignition: long base then mild breakout (RSI stays mid, pct10 modest) ---
    closes = [10.0 + (i % 3) * 0.02 for i in range(18)] + [10.05, 10.12, 10.25, 10.40]
    vols = [100.0] * 18 + [110, 130, 280, 160]
    candles = _mk_candles(closes, vols)
    # breakout bar: clear prior range
    candles[-2][2] = max(c[2] for c in candles[:-2]) * 1.02
    candles[-2][4] = candles[-2][2] * 0.995
    snap = classify_run_phase(candles, pair="TEST-USD", cfg=cfg)
    print(
        "ignition-like snap:",
        snap.phase_name,
        snap.notes,
        "rsi",
        snap.daily_rsi,
        "pct10",
        snap.pct_from_low_10d,
    )
    # early run must NOT be blocked late-phase if still <15% off lows
    if snap.phase >= PHASE_EXTENSION and (snap.pct_from_low_10d or 0) < 0.15:
        fails.append(f"early run misclassified as late: {snap}")
    g_early = apply_run_phase_buy_gate(
        "TEST-USD", 300.0, snap, current_pair_usd=0.0, cfg=cfg
    )
    if (snap.pct_from_low_10d or 0) < 0.15 and g_early.blocked:
        fails.append(f"early modest-extension buy blocked: {g_early}")

    # --- Extension: +25%+ from lows over ~2 weeks ---
    base = [8.0 + (i % 2) * 0.02 for i in range(14)]
    run = [8.1 * (1.0 + 0.025 * i) for i in range(12)]  # ~+30% grind
    closes2 = base + run
    candles2 = _mk_candles(closes2, [100 + i * 5 for i in range(len(closes2))])
    snap2 = classify_run_phase(candles2, pair="EXT-USD", cfg=cfg)
    print(
        "extension snap:",
        snap2.phase_name,
        f"pct10={snap2.pct_from_low_10d:.3f}",
        "rsi",
        snap2.daily_rsi,
    )
    if snap2.phase < PHASE_EXTENSION:
        fails.append(
            f"expected extension+, got {snap2.phase_name} pct10={snap2.pct_from_low_10d}"
        )

    g2 = apply_run_phase_buy_gate("EXT-USD", 500.0, snap2, current_pair_usd=0.0, cfg=cfg)
    print("extension gate:", g2.as_dict())
    if not g2.blocked or g2.final_usd != 0:
        fails.append(f"extension NEW buy must block, got {g2}")

    # add into existing while extended also blocked (P0)
    g2a = apply_run_phase_buy_gate("EXT-USD", 500.0, snap2, current_pair_usd=200.0, cfg=cfg)
    if g2a.final_usd != 0:
        fails.append(f"extension ADD should block under P0, got {g2a.final_usd}")

    # --- Real LINK candles: Aug 24 must be late ---
    try:
        link = fetch_daily_candles_public("LINK-USD", limit=40)
        # find 2026-08-24 index
        from datetime import datetime, timezone

        idx24 = None
        for i, r in enumerate(link):
            d = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%Y-%m-%d")
            if d == "2026-08-24":
                idx24 = i
        if idx24 is None:
            idx24 = len(link) - 1
        snap24 = classify_run_phase(link, pair="LINK-USD", cfg=cfg, as_of_index=idx24)
        print(
            "LINK Aug24:",
            snap24.phase_name,
            f"rsi={snap24.daily_rsi}",
            f"pct10={snap24.pct_from_low_10d}",
            f"off_peak={snap24.off_peak_pct}",
            snap24.notes,
        )
        if snap24.phase < PHASE_EXTENSION:
            fails.append(f"LINK Aug24 must be phase>=3, got {snap24.phase_name}")
        g24 = apply_run_phase_buy_gate(
            "LINK-USD", 1925.0, snap24, current_pair_usd=0.0, cfg=cfg
        )
        if not g24.blocked:
            fails.append("LINK Aug24 full-wallet BUY must block")
        print("LINK Aug24 gate final", g24.final_usd, "blocked", g24.blocked)

        # early window ~ Aug 11
        idx11 = None
        for i, r in enumerate(link):
            d = datetime.fromtimestamp(r["t"], tz=timezone.utc).strftime("%Y-%m-%d")
            if d == "2026-08-11":
                idx11 = i
        if idx11 is not None:
            snap11 = classify_run_phase(link, pair="LINK-USD", cfg=cfg, as_of_index=idx11)
            print("LINK Aug11:", snap11.phase_name, snap11.pct_from_low_10d, snap11.daily_rsi)
            g11 = apply_run_phase_buy_gate(
                "LINK-USD", 300.0, snap11, current_pair_usd=0.0, cfg=cfg
            )
            # early should generally allow (phase < 3)
            if snap11.phase >= PHASE_EXTENSION:
                print("NOTE: Aug11 already extension under thresholds — check")
            else:
                if g11.blocked:
                    fails.append(f"LINK Aug11 should allow deploy, phase={snap11.phase_name}")
    except Exception as e:
        fails.append(f"LINK live candle test failed: {e}")

    # --- multi action filter ---
    acts, res = apply_run_phase_to_actions(
        [
            {"pair": "EXT-USD", "action": "BUY", "usd": 400, "reason": "t"},
            {"pair": "OK-USD", "action": "SELL", "usd": 100},
        ],
        positions_usd={},
        candles_by_pair={"EXT-USD": candles2, "OK-USD": _mk_candles([10.0] * 20)},
        cfg=cfg,
    )
    print("filtered actions", acts)
    if any(a.get("pair") == "EXT-USD" for a in acts):
        fails.append("EXT BUY should be stripped")
    if not any(a.get("pair") == "OK-USD" for a in acts):
        fails.append("SELL should pass through")

    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
