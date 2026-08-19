#!/usr/bin/env python3
"""Runner capital event detection + rebalance decision logging (isolation)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.decision_context import build_rebalance_context
from phase6.core.portfolio_external_flows import classify_external_flow_usd
from phase6.core.runner_capital_events import (
    detect_external_flow,
    process_runner_capital_events,
    snapshot_nav_from_runner,
)


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
    def __init__(self, holdings: float):
        self._h = holdings

    def get_enriched_positions(self):
        if self._h <= 0:
            return {}
        return {"OP-USD": {"value_usd": self._h}}


def test_detect_deposit_1000():
    prev = {"cash_usd": 0.0, "holdings_usd": 682.0, "total_usd": 682.0}
    cur = {"cash_usd": 1000.0, "holdings_usd": 682.0, "total_usd": 1682.0}
    flow, d = detect_external_flow(prev, cur)
    assert abs(flow - 1000.0) < 0.01, (flow, d)
    assert classify_external_flow_usd(d["delta_total"], d["delta_cash"], d["delta_holdings"]) == flow


def test_rebalance_not_external():
    prev = {"cash_usd": 500.0, "holdings_usd": 500.0, "total_usd": 1000.0}
    cur = {"cash_usd": 200.0, "holdings_usd": 800.0, "total_usd": 1000.0}
    flow, _ = detect_external_flow(prev, cur)
    assert abs(flow) < 0.01, flow


def test_process_forces_rebalance():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "runner_state.json"
        state.write_text(
            json.dumps(
                {
                    "capital_nav_snapshot": {
                        "cash_usd": 0,
                        "holdings_usd": 680,
                        "total_usd": 680,
                        "ts": "2026-07-09T00:00:00+00:00",
                    }
                }
            )
        )
        runner = SimpleNamespace(
            exchange=FakeExchange(1000.0),
            portfolio=FakePortfolio(679.0),
            config_dict={
                "global_settings": {
                    "capital_event_force_rebalance": True,
                    "capital_event_deposit_deploy_cap_usd": 0,
                }
            },
            state_file=str(state),
            shadow_mode=True,
            FIXED_UNIVERSE=["OP-USD", "LINK-USD"],
        )
        runner._force_next_rebalance = False
        events = process_runner_capital_events(runner)
        assert len(events) == 1
        assert events[0]["event_type"] == "deposit"
        assert abs(events[0]["amount_usd"] - 1000.0) < 50
        assert runner._force_next_rebalance is True
        assert len(runner._capital_events_for_decision) == 1


def test_decision_context_includes_capital_events():
    runner = SimpleNamespace(
        account_id="acct",
        trader_id="t1",
        _capital_events_for_decision=[
            {"event_type": "deposit", "amount_usd": 1000.0, "action": "force_rebalance_scheduled"}
        ],
        rsi_values={},
    )
    ctx = build_rebalance_context(
        runner=runner,
        path="arch4_rotation",
        actions_taken=[],
        executed_count=0,
    )
    assert ctx.get("capital_events") and ctx["capital_events"][0]["event_type"] == "deposit"


def test_snapshot_nav():
    runner = SimpleNamespace(
        exchange=FakeExchange(1000.0),
        portfolio=FakePortfolio(679.0),
    )
    snap = snapshot_nav_from_runner(runner)
    assert snap["cash_usd"] == 1000.0
    assert snap["holdings_usd"] == 679.0


if __name__ == "__main__":
    test_detect_deposit_1000()
    test_rebalance_not_external()
    test_process_forces_rebalance()
    test_decision_context_includes_capital_events()
    test_snapshot_nav()
    print("ALL PASS")