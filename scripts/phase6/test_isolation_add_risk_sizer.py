#!/usr/bin/env python3
"""Isolation: factor-based add risk sizer (existing stacks)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.add_risk_sizer import (
    decide_add_size,
    filter_trade_plan_add_risk,
    resolve_add_risk_factors,
    compute_max_add_usd,
    report_open_pairs_add_room,
)


def test_bull_clips_fat_link_style_add():
    factors = resolve_add_risk_factors(
        regime="bull",
        regime_entry={"rebalance_cap_usd": 100.0, "min_cash_reserve_pct": 0.10},
        rebalance_cap_usd=100.0,
        min_cash_reserve_pct=0.10,
    )
    # Old small winner + huge proposed add (mirrors pre-fix force rebalance shape)
    dec = decide_add_size(
        pair="LINK-USD",
        proposed_usd=1028.0,
        position_usd=289.0,
        entry_price=8.277,
        current_price=11.64,
        stop_price=8.028,
        equity_usd=2470.0,
        cash_usd=2107.0,
        factors=factors,
        other_book_heat_usd=20.0,
    )
    assert dec.action == "clip", dec
    assert dec.final_usd < 250, dec
    assert dec.final_usd >= 50, dec  # above min_move in typical path
    # Must be far below the cash dump
    assert dec.final_usd < 400, dec


def test_new_pair_unchanged():
    factors = resolve_add_risk_factors(regime="bull")
    dec = decide_add_size(
        pair="ETH-USD",
        proposed_usd=200.0,
        position_usd=0.0,
        entry_price=0.0,
        current_price=3000.0,
        stop_price=None,
        equity_usd=2500.0,
        cash_usd=2000.0,
        factors=factors,
    )
    assert dec.action == "unchanged_new", dec
    assert dec.final_usd == 200.0, dec


def test_bear_skips_pyramid():
    factors = resolve_add_risk_factors(regime="bear")
    dec = decide_add_size(
        pair="LINK-USD",
        proposed_usd=100.0,
        position_usd=300.0,
        entry_price=8.0,
        current_price=11.0,
        stop_price=8.0,
        equity_usd=2500.0,
        cash_usd=2000.0,
        factors=factors,
    )
    assert dec.action == "skip", dec
    assert dec.final_usd == 0.0, dec


def test_tight_gap_skips():
    factors = resolve_add_risk_factors(regime="bull")
    dec = decide_add_size(
        pair="X-USD",
        proposed_usd=100.0,
        position_usd=200.0,
        entry_price=10.0,
        current_price=10.1,
        stop_price=10.0,  # ~1% gap
        equity_usd=2500.0,
        cash_usd=1000.0,
        factors=factors,
    )
    assert dec.action == "skip", dec


def test_over_target_zero_room():
    factors = resolve_add_risk_factors(
        regime="bull",
        rebalance_cap_usd=500.0,
        min_cash_reserve_pct=0.10,
    )
    # Already 50%+ of book
    max_add, detail = compute_max_add_usd(
        pair="LINK-USD",
        position_usd=1300.0,
        entry_price=10.9,
        current_price=11.64,
        stop_price=8.028,
        equity_usd=2470.0,
        cash_usd=1078.0,
        factors=factors,
        other_book_heat_usd=50.0,
    )
    assert max_add == 0.0 or max_add < factors.min_move_usd, (max_add, detail)
    assert detail.get("exposure_room", 1) == 0.0 or max_add == 0.0


def test_filter_plan_clips():
    factors_rm = {
        "add_risk_sizer_enabled": True,
        "stop_loss_pct": 0.03,
        "near_stop_min_gap_pct": 0.02,
        "add_risk": {
            "k_profit": 0.33,
            "h_add": 0.02,
            "H_book": 0.06,
            "target_pair_weight": 0.22,
            "cash_frac": 0.25,
            "allow_pyramid": True,
            "min_move_usd": 50.0,
            "min_position_usd": 25.0,
        },
    }

    class _Plan:
        def __init__(self):
            self.actions = [
                {"pair": "LINK-USD", "action": "BUY", "usd": 1000.0, "reason": "opportunistic_rotation_from_weak"},
                {"pair": "ETH-USD", "action": "BUY", "usd": 150.0, "reason": "new"},
                {"pair": "SOL-USD", "action": "SELL", "usd": 40.0, "reason": "exit"},
            ]

    class _Port:
        def get_enriched_positions(self):
            return {
                "positions": {
                    "LINK-USD": {
                        "value_usd": 289.0,
                        "entry_price": 8.277,
                        "current_price": 11.64,
                        "amount": 24.83,
                    }
                },
                "cash_usd": 2107.0,
            }

    runner = SimpleNamespace(
        portfolio=_Port(),
        exchange=None,
        config_dict={
            "risk_management": factors_rm,
            "global_settings": {"rebalance_cap_usd": 100.0},
        },
        last_total_equity=2470.0,
    )

    # Monkeypatch regime load to bull without file dependency flaking
    import phase6.core.add_risk_sizer as ars

    real = ars._load_factors_for_runner

    def _fake(runner):
        return resolve_add_risk_factors(
            regime="bull",
            risk_management=factors_rm,
            rebalance_cap_usd=100.0,
            min_cash_reserve_pct=0.10,
        )

    ars._load_factors_for_runner = _fake
    real_stop = ars._stop_for_pair
    ars._stop_for_pair = lambda pair, entry, sl: 8.028 if "LINK" in pair else None
    try:
        plan = filter_trade_plan_add_risk(runner, _Plan())
        by_pair = {a["pair"]: a for a in plan.actions}
        assert "ETH-USD" in by_pair and by_pair["ETH-USD"]["usd"] == 150.0
        assert "SOL-USD" in by_pair
        link = by_pair.get("LINK-USD")
        assert link is not None, plan.actions
        assert float(link["usd"]) < 250, link
        assert float(link["usd"]) <= 100.0 + 1e-6, link  # rebalance cap binds or tighter
    finally:
        ars._load_factors_for_runner = real
        ars._stop_for_pair = real_stop


def test_open_pairs_report_marks_over_target():
    factors = resolve_add_risk_factors(
        regime="bull",
        rebalance_cap_usd=100.0,
        min_cash_reserve_pct=0.10,
    )
    rows = report_open_pairs_add_room(
        positions=[
            {
                "pair": "LINK-USD",
                "value_usd": 1306.0,
                "entry_price": 10.89,
                "current_price": 11.64,
            },
            {
                "pair": "PAXG-USD",
                "value_usd": 85.0,
                "entry_price": 4055.0,
                "current_price": 4617.0,
            },
            {
                "pair": "ADA-USD",
                "value_usd": 0.04,
                "entry_price": 0.16,
                "current_price": 0.22,
            },
        ],
        equity_usd=2470.0,
        cash_usd=1078.0,
        factors=factors,
        stops={"LINK-USD": 8.028, "PAXG-USD": 3937.0},
    )
    by = {r["pair"]: r for r in rows}
    assert by["LINK-USD"]["over_target"] is True
    assert by["LINK-USD"]["max_add_usd"] == 0.0 or by["LINK-USD"]["max_add_usd"] < 50
    assert by["ADA-USD"]["status"] == "dust_or_flat"
    assert by["PAXG-USD"]["max_add_usd"] is not None


def main() -> int:
    test_bull_clips_fat_link_style_add()
    test_new_pair_unchanged()
    test_bear_skips_pyramid()
    test_tight_gap_skips()
    test_over_target_zero_room()
    test_filter_plan_clips()
    test_open_pairs_report_marks_over_target()
    print("PASS add_risk_sizer isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
