"""Isolation: powder balancer plan + transition wiring (no live orders)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.powder_balancer import (
    ACTION_HOLD,
    ACTION_PARK_TO_USDC,
    ACTION_TOPUP_FROM_USDC,
    compute_target_usd_reserve,
    compute_wave_need,
    plan_powder_balance,
    powder_balancer_cfg,
)
from phase6.core.usdc_park_transitions import (
    PHASE_POWDER_BALANCED,
    plan_usdc_park_for_daily_rebalance,
)


def test_wave_need_from_tryout_cfg():
    cfg = {
        "global_settings": {"rebalance_cap_usd": 75.0},
        "operator_override": {
            "recovery_soft_down_20260828": {
                "enabled": True,
                "quality_tryout": {
                    "abs_cap_usd": 75.0,
                    "max_new_seats_per_day": 2,
                },
            }
        },
    }
    w = compute_wave_need(cfg)
    assert w.seat_usd == 75.0
    assert w.max_concurrent_seats == 2
    assert w.wave_usd == 150.0
    assert w.source == "quality_tryout"


def test_target_reserve_floor_and_buffer():
    w = compute_wave_need(
        {
            "global_settings": {"rebalance_cap_usd": 75},
            "operator_override": {
                "recovery_soft_down_20260828": {
                    "enabled": True,
                    "quality_tryout": {"abs_cap_usd": 75, "max_new_seats_per_day": 2},
                }
            },
        }
    )
    pcfg = powder_balancer_cfg(
        {
            "powder_balancer": {
                "enabled": True,
                "auto_reserve_from_tryout": True,
                "reserve_waves": 1.0,
                "usd_reserve_buffer_usd": 50.0,
                "usd_reserve_floor_usd": 150.0,
                "usd_reserve_ceiling_usd": 400.0,
            }
        }
    )
    # 150 wave + 50 buffer = 200
    t = compute_target_usd_reserve(w, pcfg)
    assert t == 200.0


def test_plan_parks_structural_stub():
    park_cfg = {
        "enabled": True,
        "powder_balancer": {
            "enabled": True,
            "auto_reserve_from_tryout": True,
            "reserve_waves": 1.0,
            "usd_reserve_buffer_usd": 50.0,
            "usd_reserve_floor_usd": 150.0,
            "usd_reserve_ceiling_usd": 400.0,
            "min_action_usd": 25.0,
            "hysteresis_usd": 20.0,
        },
    }
    cfg = {
        "global_settings": {"rebalance_cap_usd": 75.0, "strategy_mode": "deploy"},
        "operator_override": {
            "recovery_soft_down_20260828": {
                "enabled": True,
                "quality_tryout": {"abs_cap_usd": 75.0, "max_new_seats_per_day": 2},
            }
        },
    }
    # $2210 USD, $0 USDC → park excess above ~$200 reserve
    plan = plan_powder_balance(
        usd=2210.0,
        usdc=0.0,
        crypto_usd=81.0,
        park_cfg=park_cfg,
        config_dict=cfg,
        park_master_enabled=True,
    )
    assert plan.action == ACTION_PARK_TO_USDC
    assert plan.target_usd_reserve == 200.0
    assert plan.convert_usd == 2010.0
    assert plan.structural_stub_usd == 2010.0  # cash - reserve before convert intent


def test_plan_topup_when_powder_short():
    park_cfg = {
        "enabled": True,
        "powder_balancer": {
            "enabled": True,
            "usd_reserve_usd": 200.0,
            "usd_reserve_buffer_usd": 0.0,
            "usd_reserve_floor_usd": 150.0,
            "usd_reserve_ceiling_usd": 400.0,
            "min_action_usd": 25.0,
            "hysteresis_usd": 20.0,
            "auto_reserve_from_tryout": False,
        },
    }
    plan = plan_powder_balance(
        usd=40.0,
        usdc=2000.0,
        crypto_usd=0.0,
        park_cfg=park_cfg,
        config_dict={"global_settings": {"rebalance_cap_usd": 75}},
        park_master_enabled=True,
    )
    assert plan.action == ACTION_TOPUP_FROM_USDC
    assert plan.unwind_usd >= 150.0
    assert plan.usd + plan.unwind_usd >= plan.target_usd_reserve - 1.0


def test_plan_hold_within_hysteresis():
    park_cfg = {
        "enabled": True,
        "powder_balancer": {
            "enabled": True,
            "usd_reserve_usd": 200.0,
            "usd_reserve_buffer_usd": 0.0,
            "usd_reserve_floor_usd": 150.0,
            "usd_reserve_ceiling_usd": 400.0,
            "min_action_usd": 25.0,
            "hysteresis_usd": 25.0,
            "auto_reserve_from_tryout": False,
        },
    }
    plan = plan_powder_balance(
        usd=210.0,
        usdc=1800.0,
        park_cfg=park_cfg,
        config_dict={},
        park_master_enabled=True,
    )
    assert plan.action == ACTION_HOLD


def test_disabled_no_action():
    plan = plan_powder_balance(
        usd=2000.0,
        usdc=0.0,
        park_cfg={"enabled": True, "powder_balancer": {"enabled": False}},
        park_master_enabled=True,
    )
    assert plan.action == "disabled"


def _mock_runner_deploy():
    runner = MagicMock()
    runner.config_dict = {
        "global_settings": {
            "strategy_mode": "deploy",
            "rebalance_cap_usd": 75.0,
            "risk_free_preference": "USD",
        },
        "_analyst_shadow": {"scenario_id": "defensive_rotation_21d"},
        "operator_override": {
            "recovery_soft_down_20260828": {
                "enabled": True,
                "quality_tryout": {"abs_cap_usd": 75.0, "max_new_seats_per_day": 2},
            }
        },
    }
    runner.mode = "shadow"
    runner.exchange = MagicMock()
    runner.exchange.get_account_balance = lambda c: {"USD": 2210.0, "USDC": 0.0}.get(c, 0)
    runner.FIXED_UNIVERSE = ["BTC-USD", "ETH-USD"]
    runner.portfolio = MagicMock()
    runner.portfolio.get_enriched_positions.return_value = {
        "positions": {"PAXG-USD": {"value_usd": 81.0}}
    }
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
    runner.account_id = "iso-powder-acct"
    return runner


def test_transition_runs_powder_on_deploy():
    runner = _mock_runner_deploy()
    park = {
        "enabled": True,
        "usdc_product_id": "USDC-USD",
        "powder_balancer": {
            "enabled": True,
            "auto_reserve_from_tryout": True,
            "reserve_waves": 1.0,
            "usd_reserve_buffer_usd": 50.0,
            "usd_reserve_floor_usd": 150.0,
            "usd_reserve_ceiling_usd": 400.0,
            "min_action_usd": 25.0,
            "hysteresis_usd": 20.0,
        },
    }
    with patch(
        "phase6.core.usdc_park_transitions.live_usdc_park_settings",
        return_value=park,
    ):
        plan = plan_usdc_park_for_daily_rebalance(runner)
    assert plan.run_powder_balance is True
    assert plan.run_park is False
    assert plan.run_redeploy_unwind is False
    assert plan.operational_phase == PHASE_POWDER_BALANCED
    assert plan.powder_summary is not None
    assert plan.powder_summary.get("action") == ACTION_PARK_TO_USDC
    # shadow mode must not place live-looking success without skip
    assert plan.powder_summary.get("skipped") is True
    # never sold alts
    runner.order_executor.execute_sell.assert_not_called()


def test_transition_park_signal_still_full_park():
    runner = _mock_runner_deploy()
    runner.config_dict["global_settings"]["strategy_mode"] = "usdc_park"
    runner.config_dict["global_settings"]["rebalance_cap_usd"] = 0.0
    runner.config_dict["_analyst_shadow"] = {"scenario_id": "usdc_hold"}
    park = {
        "enabled": True,
        "min_usd_reserve_usd": 50.0,
        "target_usdc_pct": 0.92,
        "min_sell_usd": 15.0,
        "skip_if_usdc_pct_above": 0.99,
        "powder_balancer": {"enabled": True},
    }
    with patch(
        "phase6.core.usdc_park_transitions.live_usdc_park_settings",
        return_value=park,
    ):
        plan = plan_usdc_park_for_daily_rebalance(runner)
    assert plan.run_park is True
    assert plan.run_powder_balance is False


if __name__ == "__main__":
    test_wave_need_from_tryout_cfg()
    test_target_reserve_floor_and_buffer()
    test_plan_parks_structural_stub()
    test_plan_topup_when_powder_short()
    test_plan_hold_within_hysteresis()
    test_disabled_no_action()
    test_transition_runs_powder_on_deploy()
    test_transition_park_signal_still_full_park()
    print("powder_balancer isolation PASS")
