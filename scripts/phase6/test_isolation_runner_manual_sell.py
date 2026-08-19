#!/usr/bin/env python3
"""Isolation: runner detects manual liquidation and sets hold + cooldown."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.runner_capital_events import process_runner_capital_events


class FakeExchange:
    def __init__(self, usd: float, usdc: float = 0.0):
        self._usd = usd
        self._usdc = usdc

    def get_account_balance(self, cur: str):
        if cur == "USD":
            return self._usd
        if cur == "USDC":
            return self._usdc
        return 0.0


class FakePortfolio:
    def __init__(self, holdings_usd: float, positions: dict):
        self._hold = holdings_usd
        self._pos = positions

    def get_total_value(self):
        return self._hold

    def get_enriched_positions(self):
        return self._pos


def test_manual_liquidation_cycle():
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "phase6_runner_state.json"
        ledger = Path(td) / "empty_trades.jsonl"
        ledger.write_text("")
        state.write_text(
            json.dumps(
                {
                    "capital_nav_snapshot": {
                        "cash_usd": 50.0,
                        "holdings_usd": 650.0,
                        "total_usd": 700.0,
                    },
                    "capital_position_snapshot": {
                        "positions": {"OP-USD": 400.0, "LINK-USD": 250.0},
                    },
                }
            )
        )
        runner = MagicMock()
        runner.state_file = str(state)
        runner.config_dict = {
            "global_settings": {
                "capital_event_min_flow_usd": 50.0,
                "capital_event_manual_sell_hold_cash": True,
                "capital_event_manual_sell_block_rebuy_hours": 48,
                "capital_event_manual_sell_cancel_stops": False,
                "capital_event_ledger_jsonl_path": str(ledger),
            },
            "withdrawal_reserve": {"min_reserve_usd": 50.0},
        }
        runner.shadow_mode = True
        runner.exchange = FakeExchange(usd=430.0)
        runner.portfolio = FakePortfolio(
            270.0,
            {"OP-USD": 0.0, "LINK-USD": 270.0},
        )
        runner.stop_loss_coordinator = MagicMock(client=None)
        runner._get_recently_stopped_pairs = MagicMock(return_value=[])

        events = process_runner_capital_events(runner)
        assert len(events) == 1
        assert events[0]["event_type"] == "manual_liquidation_to_cash"
        assert getattr(runner, "_manual_liquidation_cash_hold_usd", 0) > 0
        data = json.loads(state.read_text())
        assert "OP-USD" in (data.get("manual_sell_cooldown") or {})
        print("PASS runner manual liquidation")


if __name__ == "__main__":
    test_manual_liquidation_cycle()
    print("ALL PASS")