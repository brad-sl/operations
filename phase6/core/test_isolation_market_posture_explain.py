#!/usr/bin/env python3
"""Isolation: why_idle + heat posture (no network required for core classify)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.market_posture_explain import build_why_idle


def test_why_idle_park_hot():
    why = build_why_idle(
        rc={
            "regime": "transition",
            "regime_layer": "soft_up",
            "strategy_mode": "usdc_park",
            "allow_new_buys": False,
            "rebalance_cap_usd": 0,
            "btc_return_pct": 9.2,
            "shadow_stance": "flat_b_tight",
        },
        shadow={"shadow_would_buy_count": 0, "shadow_would_buy_pairs": [], "live": {"would_buy_count": 0}},
        heat={
            "hot": True,
            "btc_change_24h_pct": 6.1,
            "median_change_24h_pct": 8.0,
            "top_movers": [
                {"pair": "XRP-USD", "change_24h_pct": 17.0},
                {"pair": "HYPE-USD", "change_24h_pct": 15.0},
            ],
            "note": "test",
        },
        live={"total_usd": 2500, "cash_usd": 2100, "total_holdings_value": 400, "trading_positions": [{"pair": "LINK-USD", "value_usd": 300}]},
        basket=["BTC-USD", "ETH-USD", "XRP-USD", "LINK-USD"],
    )
    codes = {r["code"] for r in why["reasons"]}
    assert "stance_park" in codes
    assert "cream_empty" in codes
    assert "not_in_bag" in codes  # HYPE outside bag
    assert why["heat"]["hot"] is True
    assert "cash" in why["headline"].lower()
    assert "PARK" not in why["headline"]
    assert "usdc_park" not in (why["reasons"][0].get("detail") or "")
    print("  why_idle park+hot OK (plain English)")


def test_why_idle_deploy_empty_entry():
    why = build_why_idle(
        rc={
            "regime": "flat",
            "regime_layer": "flat",
            "strategy_mode": "deploy",
            "allow_new_buys": True,
            "rebalance_cap_usd": 75,
            "btc_return_pct": 2.0,
            "shadow_stance": "flat_b",
        },
        shadow={"shadow_would_buy_count": 0, "shadow_would_buy_pairs": [], "live": {"would_buy_count": 0}},
        heat={"hot": False, "btc_change_24h_pct": 0.5, "top_movers": [], "note": ""},
        live={"total_usd": 2500, "cash_usd": 500, "total_holdings_value": 2000, "trading_positions": []},
        basket=["BTC-USD"],
    )
    codes = {r["code"] for r in why["reasons"]}
    assert "stance_deploy" in codes
    assert "entry_gates" in codes
    assert "RSI" not in why["headline"]
    # No hard dollar cycle promise (cap is soft; recovery can exceed)
    blob = " ".join(
        f"{r.get('title','')} {r.get('detail','')}" for r in why["reasons"]
    ).lower()
    assert "this cycle" not in blob
    assert "up to about $" not in blob
    assert "cap $" not in blob
    print("  why_idle deploy empty OK (plain English, no false $ cap)")


if __name__ == "__main__":
    test_why_idle_park_hot()
    test_why_idle_deploy_empty_entry()
    print("market_posture_explain isolation PASS")
