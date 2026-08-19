#!/usr/bin/env python3
"""Isolation: post-SL rebuy block hours must follow config (not hardcoded 24h).

GAP-05 follow-on: enforce_config_72h — recovery + deposit redeploy paths.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import rebalance_coordinator as rc  # noqa: E402
from phase6.core import runner_capital_events as rce  # noqa: E402


def test_no_hardcoded_24h_cooldown_call_in_recovery_path() -> None:
    src = inspect.getsource(rc)
    # Recovery path must not pin hours=24 on get_deployment_cooldown_pairs
    assert "get_deployment_cooldown_pairs(runner, hours=24)" not in src, (
        "recovery path still hardcodes hours=24 — use config default via get_deployment_cooldown_pairs(runner)"
    )
    assert "get_deployment_cooldown_pairs(runner)" in src
    print("PASS recovery path uses config cooldown hours")


def test_deposit_redeploy_uses_shared_cooldown_helper() -> None:
    src = inspect.getsource(rce)
    assert "hours=24" not in src or "_get_recently_stopped_pairs(hours=24)" not in src
    # deposit path should call get_deployment_cooldown_pairs
    assert "get_deployment_cooldown_pairs(runner)" in src
    print("PASS deposit redeploy uses get_deployment_cooldown_pairs")


def test_get_deployment_cooldown_pairs_default_72() -> None:
    runner = MagicMock()
    runner.state_file = str(ROOT / "data" / "state" / "phase6_runner_state.json")
    runner.config_dict = {
        "capital_event_stop_loss_exchange_block_rebuy_hours": 72,
        "capital_event_stop_loss_exchange_hold_cash": True,
    }
    runner._get_recently_stopped_pairs = MagicMock(return_value=["AAA-USD"])
    # Avoid file side effects from manual cooldown load
    blocked = rce.get_deployment_cooldown_pairs(runner)
    runner._get_recently_stopped_pairs.assert_called()
    call_kw = runner._get_recently_stopped_pairs.call_args
    hours = call_kw.kwargs.get("hours") if call_kw.kwargs else call_kw[1].get("hours") if len(call_kw) > 1 else call_kw[0][0]
    if hours is None and call_kw.args:
        hours = call_kw.args[0] if not isinstance(call_kw.args[0], int) else call_kw.args[0]
    # call is hours=int(hours)
    assert call_kw.kwargs.get("hours") == 72 or (
        call_kw.args and call_kw.args[0] == 72
    ) or call_kw == runner._get_recently_stopped_pairs.call_args
    # Prefer kwargs
    h = call_kw.kwargs.get("hours")
    if h is None and call_kw.args:
        h = call_kw.args[0]
    assert h == 72, f"expected hours=72 got {call_kw}"
    assert "AAA-USD" in blocked
    print("PASS default block hours=72 forwarded to ledger lookup")


def test_filter_blocks_buy_inside_window() -> None:
    runner = MagicMock()
    runner.state_file = str(ROOT / "data" / "state" / "phase6_runner_state.json")
    runner.config_dict = {"capital_event_stop_loss_exchange_block_rebuy_hours": 72}
    runner._get_recently_stopped_pairs = MagicMock(return_value=["SOL-USD"])

    class Plan:
        def __init__(self):
            self.actions = [
                {"pair": "SOL-USD", "action": "BUY", "usd": 75.0},
                {"pair": "BTC-USD", "action": "BUY", "usd": 75.0},
                {"pair": "ETH-USD", "action": "SELL", "usd": 40.0},
            ]

    plan = rce.filter_trade_plan_manual_cooldown(runner, Plan())
    pairs = {(a["pair"], a["action"].upper()) for a in plan.actions}
    assert ("SOL-USD", "BUY") not in pairs
    assert ("BTC-USD", "BUY") in pairs
    assert ("ETH-USD", "SELL") in pairs
    print("PASS filter strips blocked BUY, keeps other actions")


if __name__ == "__main__":
    test_no_hardcoded_24h_cooldown_call_in_recovery_path()
    test_deposit_redeploy_uses_shared_cooldown_helper()
    test_get_deployment_cooldown_pairs_default_72()
    test_filter_blocks_buy_inside_window()
    print("ALL GAP-05 ENFORCE ISOLATION CHECKS PASSED")
