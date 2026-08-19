"""Isolation: USDC park toggle + transition planner."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.usdc_park_executor import park_signal_active
from phase6.core.usdc_park_transitions import (
    deploy_signal_active,
    plan_usdc_park_for_daily_rebalance,
    record_toggle_change,
    PHASE_ARMED,
    PHASE_STANDDOWN,
)


def _mock_runner(park: bool, cap: float = 0):
    runner = MagicMock()
    runner.config_dict = {
        "global_settings": {
            "strategy_mode": "usdc_park" if park else "rotation",
            "rebalance_cap_usd": cap,
            "risk_free_preference": "USDC" if park else "USD",
        },
        "_analyst_shadow": {"scenario_id": "usdc_hold" if park else "defensive_rotation_21d"},
    }
    runner.mode = "shadow"
    runner.exchange = MagicMock()
    runner.exchange.get_account_balance = lambda c: {"USD": 200, "USDC": 700}.get(c, 0)
    runner.FIXED_UNIVERSE = ["BTC-USD"]
    runner.portfolio = MagicMock()
    runner.portfolio.get_enriched_positions.return_value = {"positions": {}}
    runner.portfolio.refresh = MagicMock()
    runner.stop_loss_coordinator = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=None)
    runner.stop_loss_coordinator.suspend_reattach_context.return_value = ctx
    runner.order_executor = MagicMock()
    runner.order_executor.execute_sell.return_value = {"success": True}
    runner.order_executor.execute_buy.return_value = {"success": True}
    runner.use_platform_executor = False
    runner.account_id = "iso-acct"
    return runner


def test_signals():
    assert park_signal_active({"global_settings": {"strategy_mode": "usdc_park", "rebalance_cap_usd": 0}})
    assert deploy_signal_active({"global_settings": {"rebalance_cap_usd": 100, "strategy_mode": "rotation"}})


def test_toggle_off_no_park():
    runner = _mock_runner(park=True)
    with patch(
        "phase6.core.usdc_park_transitions.live_usdc_park_settings",
        return_value={"enabled": False},
    ):
        plan = plan_usdc_park_for_daily_rebalance(runner)
    assert not plan.run_park


def test_off_to_on_records():
    aid = "iso-toggle-acct"
    record_toggle_change(aid, True)
    from phase6.core.usdc_park_transitions import load_transition_state

    st = load_transition_state(aid)
    assert st.get("last_transition") == "off_to_on"
    assert st.get("operational_phase") == PHASE_ARMED


if __name__ == "__main__":
    test_signals()
    test_toggle_off_no_park()
    test_off_to_on_records()
    print("usdc_park transitions isolation PASS")