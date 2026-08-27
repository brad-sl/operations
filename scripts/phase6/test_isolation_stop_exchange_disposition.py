#!/usr/bin/env python3
"""Isolation: exchange stop fills — default skip hold; TG-03 hold+72h when enabled."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.runner_capital_events import apply_manual_disposition, split_disposition_pairs_by_ledger


def test_split_and_apply_stop_exchange():
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "AVAX-USD",
                    "side": "SELL",
                    "reason": "stop_loss_exchange",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
        stop, tp, manual = split_disposition_pairs_by_ledger(
            ["AVAX-USD", "OP-USD"], window_hours=48, jsonl_path=trades
        )
        assert stop == ["AVAX-USD"], stop
        assert tp == [], tp
        assert manual == ["OP-USD"], manual

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
            "stop_loss_exchange_hold_cash": False,
            "stop_loss_exchange_block_rebuy_hours": 24.0,
            "stop_loss_ledger_lookback_hours": 48.0,
            "manual_sell_cancel_stops": False,
            "ledger_jsonl_path": str(trades),
        }
        event = {
            "event_type": "manual_liquidation_to_cash",
            "pairs_sold": ["AVAX-USD", "OP-USD"],
            "pair_deltas": {"AVAX-USD": -90.0, "OP-USD": -10.0},
            "cash_delta_usd": 100.0,
        }
        apply_manual_disposition(runner, event, settings)
        assert event["action"] == "split_stop_exchange_vs_manual"
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) == 10.0
        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "AVAX-USD" in cd and "OP-USD" in cd
        av_exp = float(cd["AVAX-USD"])
        op_exp = float(cd["OP-USD"])
        now = datetime.now(timezone.utc).timestamp()
        assert av_exp - now < 25 * 3600
        assert op_exp - now > 40 * 3600
        print("PASS stop_exchange disposition split (hold_cash=false)")


def test_stop_exchange_hold_cash_true_72h():
    """TG-03 repair: stop pairs also hold cash + longer rebuy block."""
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "SOL-USD",
                    "side": "SELL",
                    "reason": "stop_loss_exchange",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
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
            "pairs_sold": ["SOL-USD"],
            "pair_deltas": {"SOL-USD": -280.0},
            "cash_delta_usd": 280.0,
        }
        apply_manual_disposition(runner, event, settings)
        assert event["action"] == "hold_cash_block_rebuy_stop_exchange"
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) == 280.0
        assert event.get("cash_hold_added_exchange_stop_usd") == 280.0
        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "SOL-USD" in cd
        exp = float(cd["SOL-USD"])
        now = datetime.now(timezone.utc).timestamp()
        assert 70 * 3600 < exp - now < 73 * 3600
        print("PASS stop_exchange hold_cash=true 72h")


def test_take_profit_not_manual_cash_hold():
    """Live TP must not park cash hold or stamp 48h capital cooldown."""
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "LINK-USD",
                    "side": "SELL",
                    "reason": "take_profit_fixed_tp",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
        stop, tp, manual = split_disposition_pairs_by_ledger(
            ["LINK-USD"], window_hours=48, jsonl_path=trades
        )
        assert stop == []
        assert tp == ["LINK-USD"]
        assert manual == []

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
            "pairs_sold": ["LINK-USD"],
            "pair_deltas": {"LINK-USD": -1299.0},
            "cash_delta_usd": 1286.0,
        }
        apply_manual_disposition(runner, event, settings)
        assert event["action"] == "take_profit_no_cash_hold"
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) == 0.0
        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "LINK-USD" not in cd, cd
        print("PASS take_profit no cash hold / no capital cooldown")


def test_lifecycle_extension_partial_not_manual_cash_hold():
    """lifecycle_extension_partial must classify as strategy exit — never manual hold.

    BTC 2026-08-26: partial trim mis-tagged → $235 cash hold + 48h rebuy block.
    """
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "BTC-USD",
                    "side": "SELL",
                    "reason": "lifecycle_extension_partial:phase=exhaustion|mfe=0.04",
                    "signal_source": "lifecycle_extension_partial",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
        stop, tp, manual = split_disposition_pairs_by_ledger(
            ["BTC-USD"], window_hours=48, jsonl_path=trades
        )
        assert stop == [], stop
        assert tp == ["BTC-USD"], tp
        assert manual == [], manual

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
            "pair_deltas": {"BTC-USD": -235.53},
            "cash_delta_usd": 235.53,
            "sold_usd": 235.53,
        }
        apply_manual_disposition(runner, event, settings)
        assert event["action"] == "take_profit_no_cash_hold", event.get("action")
        assert event.get("action_detail") == "lifecycle_or_tp_no_cash_hold"
        assert "BTC-USD" in (event.get("pairs_lifecycle_exit") or [])
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) == 0.0
        assert float(event.get("cash_hold_skipped_take_profit_usd") or 0) == 235.53
        data = json.loads(state.read_text())
        cd = data.get("manual_sell_cooldown") or {}
        assert "BTC-USD" not in cd, cd
        print("PASS lifecycle_extension_partial no cash hold / no capital cooldown")


def test_lifecycle_dual_peak_not_manual():
    with tempfile.TemporaryDirectory() as td:
        trades = Path(td) / "trades.jsonl"
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        trades.write_text(
            json.dumps(
                {
                    "pair": "ETH-USD",
                    "side": "SELL",
                    "reason": "lifecycle_dual_peak:stall|sent_fade",
                    "timestamp": ts,
                }
            )
            + "\n"
        )
        stop, tp, manual = split_disposition_pairs_by_ledger(
            ["ETH-USD"], window_hours=48, jsonl_path=trades
        )
        assert stop == [] and tp == ["ETH-USD"] and manual == []
        print("PASS lifecycle_dual_peak classifies as tp")


if __name__ == "__main__":
    test_split_and_apply_stop_exchange()
    test_stop_exchange_hold_cash_true_72h()
    test_take_profit_not_manual_cash_hold()
    test_lifecycle_extension_partial_not_manual_cash_hold()
    test_lifecycle_dual_peak_not_manual()
    print("ALL PASS")
