#!/usr/bin/env python3
"""Isolation tests for breadth + cash re-risk shadow helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.market_breadth_breakout import (  # noqa: E402
    breadth_from_returns,
    evaluate_cash_rerisk_shadow,
)


def test_breadth_on_four_of_eight() -> None:
    rets = {
        "BTC-USD": 0.056,
        "ETH-USD": 0.09,
        "SOL-USD": 0.06,
        "XRP-USD": 0.062,
        "LINK-USD": 0.044,
        "AVAX-USD": 0.01,
        "DOGE-USD": 0.034,
        "ADA-USD": 0.0,
    }
    b = breadth_from_returns(rets, ret_min=0.03, k=4)
    assert b.breadth_on, b
    assert b.breadth_count >= 4
    print("PASS breadth ON")


def test_case_20260819_would_fire() -> None:
    """Reconstructed miss: cash ~83%, multi-major green ≥3%."""
    rets = {
        "BTC-USD": 0.0564,
        "ETH-USD": 0.0896,
        "XRP-USD": 0.0620,
        "SOL-USD": 0.0604,
        "LINK-USD": 0.0445,
        "DOGE-USD": 0.0341,
        "AVAX-USD": 0.02,
        "ADA-USD": 0.01,
    }
    b = breadth_from_returns(rets, ret_min=0.03, k=4)
    assert b.breadth_on
    fire = evaluate_cash_rerisk_shadow(
        cash_usd=2031.8,
        total_usd=2434.7,
        breadth=b,
        btc_ret_30d=0.05,
        buy_blocked=[],
        in_basket=[
            "BTC-USD",
            "ETH-USD",
            "SOL-USD",
            "XRP-USD",
            "DOGE-USD",
            "LINK-USD",
            "UNI-USD",
            "AVAX-USD",
            "ARB-USD",
            "ICP-USD",
            "RAVE-USD",
        ],
    )
    assert fire.fire, fire
    assert fire.tag == "fire"
    assert fire.paper_sleeve_usd > 0
    assert "BTC-USD" in fire.paper_targets or "ETH-USD" in fire.paper_targets
    print("PASS case would-fire", fire.paper_targets, fire.paper_sleeve_usd)


def test_blocked_all_no_fire() -> None:
    rets = {p: 0.05 for p in ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "LINK-USD"]}
    b = breadth_from_returns(rets, k=4)
    fire = evaluate_cash_rerisk_shadow(
        cash_usd=2000,
        total_usd=2400,
        breadth=b,
        btc_ret_30d=0.0,
        buy_blocked=["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LINK-USD", "AVAX-USD", "ADA-USD", "UNI-USD", "ARB-USD", "ICP-USD", "RAVE-USD"],
        in_basket=["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "LINK-USD"],
    )
    assert not fire.fire
    assert fire.tag == "blocked"
    print("PASS all blocked")


def test_bear_veto() -> None:
    rets = {p: 0.05 for p in ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]}
    b = breadth_from_returns(rets, k=4)
    fire = evaluate_cash_rerisk_shadow(
        cash_usd=2000, total_usd=2400, breadth=b, btc_ret_30d=-0.12
    )
    assert not fire.fire and fire.tag == "bear"
    print("PASS bear veto")


if __name__ == "__main__":
    test_breadth_on_four_of_eight()
    test_case_20260819_would_fire()
    test_blocked_all_no_fire()
    test_bear_veto()
    print("ALL market_breadth_breakout ISOLATION CHECKS PASSED")
