#!/usr/bin/env python3
"""Isolation: core-sleeve rotation guards + holdings USD map + rotation≠manual (Brad GO 2026-10-02).

Reproduces BTC 2026-10-01 failure modes:
1) RSI>70 ROTATE_OUT alone must NOT full-bag sell core
2) sell-only rotation (no ROTATE_IN ≥0.55) must hold core
3) exit_weak_for_rotation must NOT stamp 48h manual rebuy block
4) holdings_before must use value_usd / qty*px — never bare coin qty as USD
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_rsi_overbought_only_holds_core() -> None:
    from phase6.core.allocator import AllocatorConfig, RotationStrategy
    from phase6.core.evaluation import Proposal

    cfg = AllocatorConfig(min_move_usd=50.0, min_score_delta=0.05, cooldown_hours=0.0)
    strat = RotationStrategy(cfg)
    # BTC snapshot-class: RSI OB SELL conf 0.4, peers HOLD, ADA/LINK under buy floor
    proposals = [
        Proposal(
            pair="BTC-USD",
            side="ROTATE_OUT",
            score=0.4,
            reason="RSI overbought",
            source="signal_generator",
            confidence=0.4,
            metadata={"rsi": 71.96, "sentiment": 0.08},
        ),
        Proposal(
            pair="ETH-USD",
            side="HOLD",
            score=0.5,
            reason="No strong signal",
            source="signal_generator",
            metadata={"rsi": 55.0, "sentiment": 0.1},
        ),
        Proposal(
            pair="ADA-USD",
            side="ROTATE_IN",
            score=0.499,
            reason="scanner",
            source="opportunity_scanner",
            metadata={"rsi": 48.0, "sentiment": 0.3},
        ),
        Proposal(
            pair="LINK-USD",
            side="ROTATE_IN",
            score=0.314,
            reason="scanner",
            source="opportunity_scanner",
            metadata={"rsi": 50.0, "sentiment": 0.2},
        ),
    ]
    allocs = {
        "BTC-USD": 370.0,
        "ETH-USD": 246.0,
        "SOL-USD": 77.0,
        "PAXG-USD": 79.0,
        "HYPE-USD": 25.0,
    }
    plan = strat.decide(
        proposals=proposals,
        current_allocs=dict(allocs),
        cash_usd=500.0,
        total_capital=sum(allocs.values()) + 500.0,
    )
    sells = [a for a in plan.actions if a.get("action") == "SELL" and a.get("pair") == "BTC-USD"]
    assert not sells, f"BTC must hold on RSI-OB-only; got {plan.actions} notes={plan.notes}"
    assert "core_sleeve_rsi_ob_hold" in (plan.notes or "")
    print("PASS rsi_overbought_only_holds_core")


def test_confirmed_bearish_rsi_ob_still_rotates() -> None:
    from phase6.core.allocator import AllocatorConfig, RotationStrategy
    from phase6.core.evaluation import Proposal

    cfg = AllocatorConfig(min_move_usd=50.0, min_score_delta=0.05, cooldown_hours=0.0)
    strat = RotationStrategy(cfg)
    proposals = [
        Proposal(
            pair="BTC-USD",
            side="ROTATE_OUT",
            score=0.7,
            reason="RSI overbought | Negative sentiment",
            source="signal_generator",
            confidence=0.7,
            metadata={"rsi": 72.0, "sentiment": -0.35},
        ),
        Proposal(
            pair="ETH-USD",
            side="ROTATE_IN",
            score=0.62,
            reason="Positive sentiment",
            source="signal_generator",
            metadata={"rsi": 45.0, "sentiment": 0.4},
        ),
    ]
    # ≥3 held bags so emergency_recovery is off (else ≤2 bags bypass core-sleeve)
    plan = strat.decide(
        proposals=proposals
        + [
            Proposal(
                pair="SOL-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={"rsi": 50.0, "sentiment": 0.0},
            ),
            Proposal(
                pair="PAXG-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={"rsi": 50.0, "sentiment": 0.0},
            ),
        ],
        current_allocs={"BTC-USD": 400.0, "SOL-USD": 80.0, "PAXG-USD": 80.0},
        cash_usd=100.0,
        total_capital=660.0,
    )
    sells = [a for a in plan.actions if a.get("action") == "SELL" and a.get("pair") == "BTC-USD"]
    buys = [a for a in plan.actions if a.get("action") == "BUY" and a.get("pair") == "ETH-USD"]
    assert sells, f"confirmed bearish should rotate; got {plan.actions}"
    assert buys, f"should redeploy to ETH; got {plan.actions}"
    print("PASS confirmed_bearish_rsi_ob_still_rotates")


def test_sell_only_holds_core() -> None:
    """True weak HOLD score but no eligible ROTATE_IN → hold, don't cash-park."""
    from phase6.core.allocator import AllocatorConfig, RotationStrategy
    from phase6.core.evaluation import Proposal

    cfg = AllocatorConfig(min_move_usd=50.0, min_score_delta=0.05, cooldown_hours=0.0)
    strat = RotationStrategy(cfg)
    # Explicit weak via low HOLD score (not RSI-OB-only path)
    proposals = [
        Proposal(
            pair="SOL-USD",
            side="HOLD",
            score=0.35,  # < weak_thresh 0.45
            reason="No strong signal",
            source="signal_generator",
            metadata={"rsi": 48.0, "sentiment": 0.0},
        ),
        Proposal(
            pair="ADA-USD",
            side="ROTATE_IN",
            score=0.40,  # under normal min_buy 0.55
            reason="weak scanner",
            source="opportunity_scanner",
            metadata={"rsi": 42.0, "sentiment": 0.1},
        ),
    ]
    plan = strat.decide(
        proposals=proposals
        + [
            Proposal(
                pair="ETH-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={"rsi": 52.0, "sentiment": 0.0},
            ),
            Proposal(
                pair="PAXG-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={"rsi": 50.0, "sentiment": 0.0},
            ),
        ],
        # ≥3 bags so emergency_recovery is off
        current_allocs={"SOL-USD": 200.0, "ETH-USD": 200.0, "PAXG-USD": 80.0},
        cash_usd=300.0,
        total_capital=780.0,
    )
    sells = [a for a in plan.actions if a.get("action") == "SELL"]
    assert not sells, f"sell-only must hold core; got {plan.actions} notes={plan.notes}"
    assert "core_sleeve_sell_only_hold=1" in (plan.notes or "")
    print("PASS sell_only_holds_core")


def test_exit_weak_not_manual_48h() -> None:
    from phase6.core.runner_capital_events import (
        apply_manual_disposition,
        split_disposition_pairs_by_ledger,
        _reason_is_strategy_rotation,
    )

    assert _reason_is_strategy_rotation("exit_weak_for_rotation")
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "BTC-USD",
                    "side": "SELL",
                    "reason": "exit_weak_for_rotation",
                    "signal_source": "arch4_rotation",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
        stop, tp, manual = split_disposition_pairs_by_ledger(
            ["BTC-USD"], window_hours=48, jsonl_path=trades
        )
        assert stop == [] and manual == [] and tp == ["BTC-USD"], (stop, tp, manual)

        state = Path(td) / "state.json"
        state.write_text("{}")
        runner = MagicMock()
        runner.state_file = str(state)
        runner._manual_liquidation_cash_hold_usd = 0.0
        runner._manual_sell_cooldown = {}
        runner.stop_loss_coordinator = MagicMock(client=None)
        settings = {
            "manual_sell_hold_cash": True,
            "manual_sell_block_rebuy_hours": 48.0,
            "stop_loss_exchange_hold_cash": True,
            "stop_loss_exchange_block_rebuy_hours": 72.0,
            "stop_loss_ledger_lookback_hours": 48.0,
            "manual_sell_cancel_stops": False,
            "ledger_jsonl_path": str(trades),
        }
        event = {
            "event_type": "manual_liquidation_to_cash",
            "pairs_sold": ["BTC-USD"],
            "pair_deltas": {"BTC-USD": -366.40},
            "cash_delta_usd": 366.40,
            "sold_usd": 366.40,
        }
        apply_manual_disposition(runner, event, settings)
        assert event["action"] == "take_profit_no_cash_hold", event.get("action")
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) == 0.0
        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "BTC-USD" not in cd, cd
    print("PASS exit_weak_not_manual_48h")


def test_holdings_usd_prefers_value_not_qty() -> None:
    from phase6.core.rotation_shadow import _holdings_usd
    from phase6.core.portfolio_disposition import normalize_position_values

    # Exact failure shape: amount=qty, missing value_usd would have logged 0.023
    row = {
        "BTC-USD": {
            "amount": 0.00432136,
            "qty": 0.00432136,
            "current_price": 85558.60,
            "value_usd": 369.69,
        }
    }
    h = _holdings_usd(row)
    assert abs(h["BTC-USD"] - 369.69) < 0.02, h

    # qty*px when value_usd absent
    row2 = {
        "BTC-USD": {
            "amount": 0.00432136,
            "qty": 0.00432136,
            "current_price": 85558.60,
        }
    }
    h2 = _holdings_usd(row2)
    assert abs(h2["BTC-USD"] - (0.00432136 * 85558.60)) < 1.0, h2
    assert h2["BTC-USD"] > 100.0  # never 0.004

    # bare amount alone must NOT become USD
    row3 = {"BTC-USD": {"amount": 0.00432136, "qty": 0.00432136}}
    h3 = _holdings_usd(row3)
    assert "BTC-USD" not in h3 or h3.get("BTC-USD", 0) == 0.0, h3

    # list shape
    h4 = _holdings_usd(
        [
            {
                "pair": "BTC-USD",
                "amount": 0.004,
                "current_price": 85000.0,
                "value_usd": 340.0,
            }
        ]
    )
    assert abs(h4["BTC-USD"] - 340.0) < 0.01

    n = normalize_position_values(
        {"BTC-USD": {"amount": 0.004, "current_price": 85000.0, "value_usd": 340.0}}
    )
    assert abs(n["BTC-USD"] - 340.0) < 0.01
    n2 = normalize_position_values(
        {"BTC-USD": {"amount": 0.004, "current_price": 85000.0}}
    )
    assert abs(n2["BTC-USD"] - 340.0) < 1.0
    print("PASS holdings_usd_prefers_value_not_qty")


def test_rsi_ob_reason_variants_without_md() -> None:
    """Review #5: differently worded OB reason (no md RSI) still holds core."""
    from phase6.core.allocator import AllocatorConfig, RotationStrategy
    from phase6.core.evaluation import Proposal

    cfg = AllocatorConfig(min_move_usd=50.0, min_score_delta=0.05, cooldown_hours=0.0)
    strat = RotationStrategy(cfg)
    for reason in (
        "RSI>70 mean-reversion sell",
        "overbought RSI extension",
        "rsi_ob signal",
        "Mean reversion sell after stretch",
    ):
        proposals = [
            Proposal(
                pair="BTC-USD",
                side="ROTATE_OUT",
                score=0.4,
                reason=reason,
                source="signal_generator",
                confidence=0.4,
                metadata={"sentiment": 0.05},  # no rsi key
            ),
            Proposal(
                pair="ETH-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={},
            ),
            Proposal(
                pair="SOL-USD",
                side="HOLD",
                score=0.5,
                reason="No strong signal",
                source="signal_generator",
                metadata={},
            ),
        ]
        allocs = {"BTC-USD": 370.0, "ETH-USD": 246.0, "SOL-USD": 77.0, "PAXG-USD": 79.0}
        plan = strat.decide(
            proposals=proposals,
            current_allocs=dict(allocs),
            cash_usd=500.0,
            total_capital=sum(allocs.values()) + 500.0,
        )
        sells = [a for a in plan.actions if a.get("action") == "SELL" and a.get("pair") == "BTC-USD"]
        assert not sells, f"reason={reason!r} must hold; got {plan.actions}"
    print("PASS rsi_ob_reason_variants_without_md")


def test_emergency_thin_book_still_holds_rsi_ob() -> None:
    """Review #6: ≤2 bags emergency must NOT full-rotate on RSI-OB-only."""
    from phase6.core.allocator import AllocatorConfig, RotationStrategy
    from phase6.core.evaluation import Proposal

    cfg = AllocatorConfig(min_move_usd=50.0, min_score_delta=0.05, cooldown_hours=0.0)
    strat = RotationStrategy(cfg)
    proposals = [
        Proposal(
            pair="BTC-USD",
            side="ROTATE_OUT",
            score=0.4,
            reason="RSI overbought",
            source="signal_generator",
            confidence=0.4,
            metadata={"rsi": 72.0, "sentiment": 0.1},
        ),
        Proposal(
            pair="ETH-USD",
            side="HOLD",
            score=0.5,
            reason="No strong signal",
            source="signal_generator",
            metadata={"rsi": 50.0},
        ),
    ]
    # Only 2 held bags → emergency_recovery True historically bypassed core-sleeve
    allocs = {"BTC-USD": 370.0, "ETH-USD": 246.0}
    plan = strat.decide(
        proposals=proposals,
        current_allocs=dict(allocs),
        cash_usd=500.0,
        total_capital=sum(allocs.values()) + 500.0,
    )
    sells = [a for a in plan.actions if a.get("action") == "SELL" and a.get("pair") == "BTC-USD"]
    assert not sells, f"thin-book emergency must still hold RSI-OB BTC; got {plan.actions} notes={plan.notes}"
    assert "core_sleeve_rsi_ob_hold" in (plan.notes or "")
    print("PASS emergency_thin_book_still_holds_rsi_ob")


def main() -> int:
    test_rsi_overbought_only_holds_core()
    test_confirmed_bearish_rsi_ob_still_rotates()
    test_sell_only_holds_core()
    test_exit_weak_not_manual_48h()
    test_holdings_usd_prefers_value_not_qty()
    test_rsi_ob_reason_variants_without_md()
    test_emergency_thin_book_still_holds_rsi_ob()
    print("ALL PASS test_isolation_core_sleeve_rotation_guards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
