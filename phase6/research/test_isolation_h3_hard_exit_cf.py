#!/usr/bin/env python3
"""Isolation tests for EXIT-H3 hard-exit path counterfactual."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.research.h3_hard_exit_counterfactual import (  # noqa: E402
    decide,
    H3LegCF,
    rsi_wilder,
    walk_hard_exit_on_path,
    analyze_leg,
    load_exit_thresholds,
)


def test_rsi_climbs_to_overbought() -> None:
    # flat then strong up closes → RSI high
    closes = [100.0] * 20 + [100 + i * 3 for i in range(1, 25)]
    r = rsi_wilder(closes, 14)
    assert r[14] is not None
    assert r[-1] is not None and r[-1] > 70


def test_walk_fires_when_rsi_high() -> None:
    candles = []
    px = 100.0
    for i in range(40):
        # ramp hard after day 20
        if i > 20:
            px *= 1.04
        day = f"2026-06-{(i % 28) + 1:02d}"
        if i >= 28:
            day = f"2026-07-{(i - 27):02d}"
        candles.append(
            {
                "timestamp": day,
                "open": px,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
            }
        )
    # fix monotonic dates
    from datetime import date, timedelta

    base = date(2026, 5, 1)
    candles = []
    px = 100.0
    for i in range(50):
        if i > 25:
            px *= 1.05
        d = (base + timedelta(days=i)).isoformat()
        candles.append(
            {"timestamp": d, "open": px, "high": px * 1.01, "low": px * 0.99, "close": px}
        )
    entry = (base + timedelta(days=10)).isoformat()
    exit_d = (base + timedelta(days=45)).isoformat()
    out = walk_hard_exit_on_path(
        candles=candles,
        entry_day=entry,
        exit_day=exit_d,
        entry_px=100.0,
        overbought=70.0,
        fee_rt=0.0024,
    )
    assert out["hard_fired"] is True, out
    assert out["cf_hard_r_gross"] is not None
    assert out["cf_hard_r_net"] < out["cf_hard_r_gross"]


def test_walk_no_fire_choppy() -> None:
    from datetime import date, timedelta

    base = date(2026, 5, 1)
    candles = []
    px = 100.0
    for i in range(40):
        px = 100.0 + (1.0 if i % 2 == 0 else -1.0)
        d = (base + timedelta(days=i)).isoformat()
        candles.append(
            {"timestamp": d, "open": px, "high": px + 0.5, "low": px - 0.5, "close": px}
        )
    out = walk_hard_exit_on_path(
        candles=candles,
        entry_day=(base + timedelta(days=5)).isoformat(),
        exit_day=(base + timedelta(days=35)).isoformat(),
        entry_px=100.0,
        overbought=75.0,
        fee_rt=0.0024,
    )
    assert out["hard_fired"] is False


def test_decide_inconclusive_low_n() -> None:
    legs = [
        H3LegCF(
            pair="AAA-USD",
            entry_ts="2026-01-01T00:00:00+00:00",
            exit_ts="2026-01-10T00:00:00+00:00",
            entry_px=1.0,
            exit_px=0.97,
            realized_r=-0.03,
            reason="stop_loss_exchange",
            is_sl=True,
            regime_at_entry="bull",
            overbought_rsi=75.0,
            notional_usd=100.0,
            hard_fired=True,
            hard_day="2026-01-05",
            hard_rsi=80.0,
            cf_hard_r_gross=0.02,
            cf_hard_r_net=0.0176,
            delta_r_net=0.0476,
            delta_usd_net=4.76,
            days_held=9,
            days_to_hard=4,
            note="ok",
        )
    ]
    d = decide(legs, n_min=15)
    assert d["status"] == "inconclusive"
    assert d["recommend_live_h3_auto"] is False


def test_decide_prefer_ride() -> None:
    legs = []
    for i in range(16):
        legs.append(
            H3LegCF(
                pair=f"P{i}-USD",
                entry_ts="2026-01-01T00:00:00+00:00",
                exit_ts="2026-01-10T00:00:00+00:00",
                entry_px=1.0,
                exit_px=0.97,
                realized_r=-0.03,
                reason="stop_loss_exchange",
                is_sl=True,
                regime_at_entry="flat",
                overbought_rsi=65.0,
                notional_usd=100.0,
                hard_fired=True,
                hard_day="2026-01-03",
                hard_rsi=70.0,
                # hard exit worse: cut at -5% vs SL -3%
                cf_hard_r_gross=-0.05,
                cf_hard_r_net=-0.0524,
                delta_r_net=-0.0224,
                delta_usd_net=-2.24,
                days_held=9,
                days_to_hard=2,
                note="ok",
            )
        )
    d = decide(legs, n_min=15)
    assert d["status"] == "prefer_ride"
    assert d["recommend_live_h3_auto"] is False


def test_decide_edge_still_no_auto() -> None:
    legs = []
    for i in range(16):
        legs.append(
            H3LegCF(
                pair=f"P{i}-USD",
                entry_ts="2026-01-01T00:00:00+00:00",
                exit_ts="2026-01-10T00:00:00+00:00",
                entry_px=1.0,
                exit_px=0.97,
                realized_r=-0.03,
                reason="stop_loss_exchange",
                is_sl=True,
                regime_at_entry="bull",
                overbought_rsi=75.0,
                notional_usd=100.0,
                hard_fired=True,
                hard_day="2026-01-04",
                hard_rsi=80.0,
                cf_hard_r_gross=0.04,
                cf_hard_r_net=0.0376,
                delta_r_net=0.0676,
                delta_usd_net=6.76,
                days_held=9,
                days_to_hard=3,
                note="ok",
            )
        )
    d = decide(legs, n_min=15)
    assert d["status"] == "edge_for_hard"
    # Explicit: edge ≠ auto flip
    assert d["recommend_live_h3_auto"] is False


def test_thresholds_load_from_policy() -> None:
    th = load_exit_thresholds()
    assert "bull" in th
    assert th["bull"]["overbought_rsi"] >= 70


def test_analyze_leg_synthetic_loader() -> None:
    from datetime import date, timedelta

    base = date(2026, 4, 1)
    candles = []
    px = 10.0
    for i in range(60):
        if i > 30:
            px *= 1.04
        d = (base + timedelta(days=i)).isoformat()
        candles.append(
            {"timestamp": d, "open": px, "high": px * 1.01, "low": px * 0.99, "close": px}
        )

    def loader(_pair: str):
        return candles

    buy = {
        "pair": "LINK-USD",
        "side": "BUY",
        "timestamp": (base + timedelta(days=15)).isoformat() + "T12:00:00+00:00",
        "price": 10.0,
        "qty": 10,
    }
    sell = {
        "pair": "LINK-USD",
        "side": "SELL",
        "timestamp": (base + timedelta(days=50)).isoformat() + "T12:00:00+00:00",
        "price": 9.7,
        "qty": 10,
        "reason": "stop_loss_exchange",
        "pnl_pct": -0.03,
    }
    leg = analyze_leg(
        buy,
        sell,
        thresholds={"unknown": {"overbought_rsi": 70.0, "max_sentiment_hold": -0.2}},
        detector={"lookback_days": 30, "bull_return_pct": 15, "bear_return_pct": -10, "flat_abs_pct": 8},
        btc_closes={},
        fee_rt=0.0024,
        ohlcv_loader=loader,
    )
    assert leg is not None
    assert leg.is_sl is True
    assert leg.hard_fired is True
    assert leg.delta_r_net is not None


def main() -> int:
    test_rsi_climbs_to_overbought()
    test_walk_fires_when_rsi_high()
    test_walk_no_fire_choppy()
    test_decide_inconclusive_low_n()
    test_decide_prefer_ride()
    test_decide_edge_still_no_auto()
    test_thresholds_load_from_policy()
    test_analyze_leg_synthetic_loader()
    print("h3_hard_exit_cf isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
