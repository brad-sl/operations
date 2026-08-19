#!/usr/bin/env python3
"""Isolation: near-stop + armed-stop add block (P6-NEAR-STOP-REBALANCE-RACE-20260813)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.runner_capital_events import (
    NEAR_STOP_ADD_REASONS,
    evaluate_near_stop_add_block,
    filter_trade_plan_near_open_stop,
)

DEFAULT = {
    "enabled": True,
    "min_stop_gap_pct": 0.02,
    "max_unrealized_pct": -0.01,
    "reasons": set(NEAR_STOP_ADD_REASONS),
    "require_existing_position": True,
    "min_position_usd": 25.0,
    "stop_loss_pct": 0.03,
}


def test_link_incident_gap_blocks():
    """Aug 4 morning: buy @ 8.176 with stop 8.085 (~1.1% gap) must block."""
    r = evaluate_near_stop_add_block(
        pair="LINK-USD",
        reason="light_tilt_cash",
        position_usd=637.0,
        entry_price=8.27042687555023,
        current_price=8.176,
        stop_price=8.085,
        settings=DEFAULT,
    )
    assert r and "near_stop_gap" in r, r


def test_healthy_cushion_allows():
    r = evaluate_near_stop_add_block(
        pair="SOL-USD",
        reason="light_tilt_cash",
        position_usd=200.0,
        entry_price=70.0,
        current_price=75.0,
        stop_price=67.9,  # ~9.5% cushion
        settings=DEFAULT,
    )
    assert r is None, r


def test_unrealized_alone_blocks_when_gap_ok():
    # Wide stop gap but underwater vs SL entry past -1%
    r = evaluate_near_stop_add_block(
        pair="ETH-USD",
        reason="opportunistic_rotation_from_weak",
        position_usd=400.0,
        entry_price=100.0,
        current_price=98.5,  # -1.5% vs entry
        stop_price=90.0,  # 8.6% gap > 2%
        settings=DEFAULT,
    )
    assert r and "near_stop_unrealized" in r, r


def test_other_reason_not_blocked():
    """Pure evaluate still only soft-blocks listed reasons (armed is filter-level hard block)."""
    r = evaluate_near_stop_add_block(
        pair="LINK-USD",
        reason="rebalance_buy",
        position_usd=637.0,
        entry_price=8.27,
        current_price=8.176,
        stop_price=8.085,
        settings=DEFAULT,
    )
    assert r is None, r


def test_no_position_skips_when_required():
    r = evaluate_near_stop_add_block(
        pair="NEW-USD",
        reason="light_tilt_cash",
        position_usd=0.0,
        entry_price=0.0,
        current_price=10.0,
        stop_price=9.0,
        settings=DEFAULT,
    )
    assert r is None, r


def test_theoretical_stop_from_entry():
    # No stop_price: use entry * (1 - 3%)
    # entry 100, stop 97, px 98 → gap 1.02% < 2%
    r = evaluate_near_stop_add_block(
        pair="X-USD",
        reason="light_tilt_cash",
        position_usd=100.0,
        entry_price=100.0,
        current_price=98.0,
        stop_price=None,
        settings=DEFAULT,
    )
    assert r and "near_stop_gap" in r, r


def test_armed_stop_blocks_rebalance_add():
    """Hard gate: rebalance-style BUY (no reason or rebalance_buy) into armed registry stop must be blocked."""
    class _Plan:
        def __init__(self):
            self.actions = [
                {"pair": "RAVE-USD", "action": "BUY", "usd": 40.0, "reason": ""},
                {"pair": "RAVE-USD", "action": "BUY", "usd": 25.0, "reason": "rebalance_buy"},
                {"pair": "SOL-USD", "action": "BUY", "usd": 30.0, "reason": "light_tilt_cash"},
            ]

    class _Port:
        def get_enriched_positions(self):
            return {
                "RAVE-USD": {"value_usd": 120.0, "entry_price": 0.31, "current_price": 0.305},
                "SOL-USD": {"value_usd": 50.0, "entry_price": 70.0, "current_price": 75.0},
            }

    runner = SimpleNamespace(
        portfolio=_Port(),
        exchange=SimpleNamespace(get_price=lambda p: 0.305 if "RAVE" in p else 75.0),
        config_dict={
            "risk_management": {
                "near_stop_add_block_enabled": True,
                "near_stop_min_gap_pct": 0.02,
                "near_stop_max_unrealized_pct": -0.01,
                "near_stop_require_existing_position": True,
                "near_stop_min_position_usd": 25.0,
                "near_stop_block_reasons": ["light_tilt_cash", "opportunistic_rotation_from_weak"],
                "stop_loss_pct": 0.03,
            }
        },
    )

    import phase6.core.runner_capital_events as rce
    real = rce._latest_registry_stop_for_pair

    def _fake(pair: str):
        if pair == "RAVE-USD":
            return {"stop_price": 0.297, "entry_price": 0.31, "status": "open", "sl_order_id": "rave-sl"}
        return None

    rce._latest_registry_stop_for_pair = _fake
    try:
        plan = filter_trade_plan_near_open_stop(runner, _Plan())
        pairs = [a["pair"] for a in plan.actions]
        # RAVE adds blocked by armed (the race repro)
        assert "RAVE-USD" not in pairs, pairs
        # SOL allowed (no armed + healthy)
        assert "SOL-USD" in pairs, pairs
    finally:
        rce._latest_registry_stop_for_pair = real


def test_filter_plan_integration():
    class _Plan:
        def __init__(self):
            self.actions = [
                {
                    "pair": "LINK-USD",
                    "action": "BUY",
                    "usd": 58.0,
                    "reason": "light_tilt_cash",
                },
                {
                    "pair": "SOL-USD",
                    "action": "BUY",
                    "usd": 58.0,
                    "reason": "light_tilt_cash",
                },
                {"pair": "BTC-USD", "action": "SELL", "usd": 10.0, "reason": "exit"},
            ]

    class _Port:
        def get_enriched_positions(self):
            return {
                "LINK-USD": {
                    "value_usd": 637.0,
                    "entry_price": 8.27042687555023,
                    "current_price": 8.176,
                },
                "SOL-USD": {
                    "value_usd": 200.0,
                    "entry_price": 70.0,
                    "current_price": 75.0,
                },
            }

    runner = SimpleNamespace(
        portfolio=_Port(),
        exchange=None,
        config_dict={
            "risk_management": {
                "near_stop_add_block_enabled": True,
                "near_stop_min_gap_pct": 0.02,
                "near_stop_max_unrealized_pct": -0.01,
                "near_stop_require_existing_position": True,
                "near_stop_min_position_usd": 25.0,
                "near_stop_block_reasons": [
                    "light_tilt_cash",
                    "opportunistic_rotation_from_weak",
                ],
                "stop_loss_pct": 0.03,
            }
        },
    )
    # Monkeypatch: LINK armed (hard block), SOL no armed (gap healthy keeps it)
    import phase6.core.runner_capital_events as rce

    real = rce._latest_registry_stop_for_pair

    def _fake(pair: str):
        if pair == "LINK-USD":
            return {
                "stop_price": 8.085,
                "entry_price": 8.27042687555023,
                "status": "open",
                "sl_order_id": "incident-sl-001",
            }
        if pair == "SOL-USD":
            return None
        return None

    rce._latest_registry_stop_for_pair = _fake
    try:
        plan = filter_trade_plan_near_open_stop(runner, _Plan())
        pairs = [a["pair"] for a in plan.actions]
        assert "LINK-USD" not in pairs, pairs
        assert "SOL-USD" in pairs, pairs
        assert "BTC-USD" in pairs, pairs
    finally:
        rce._latest_registry_stop_for_pair = real


def main() -> int:
    test_link_incident_gap_blocks()
    test_healthy_cushion_allows()
    test_unrealized_alone_blocks_when_gap_ok()
    test_other_reason_not_blocked()
    test_no_position_skips_when_required()
    test_theoretical_stop_from_entry()
    test_armed_stop_blocks_rebalance_add()
    test_filter_plan_integration()
    print("PASS near_stop_add_block isolation (armed + soft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
