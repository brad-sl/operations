#!/usr/bin/env python3
"""Isolation: tryout scale-up LIVE path. No network. No real orders."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import tryout_scale_up_live as live  # noqa: E402
from phase6.core import tryout_scale_up_shadow as shadow  # noqa: E402


def _would(pair="ZEC-USD", held=25.0, step=25.0, r=0.02):
    return {
        "pair": pair,
        "status": "would_scale",
        "held_usd": held,
        "step_usd": step,
        "unrealized_r": r,
        "hold_hours": 5.0,
        "phase": 1,
        "structure_ok": True,
        "reasons": ["earned_mid_flight_step"],
    }


def test_not_armed_blocks_plan():
    decision = {
        "schema": "tryout_scale_up_brad_decision_v1",
        "live_apply": False,
        "cf_bar": {"require": False, "min_scored": 8, "max_waived_steps": 2, "waived_steps_used": 0},
    }
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 0, "usd_spent": 0.0, "pairs": [], "events": []
    }), patch.object(shadow, "_load_json", return_value={"lots": {}}), patch.object(
        live, "_write_json"
    ):
        p = live.plan_live_steps(
            decisions=[_would()],
            board={"cf": {"n": 0, "edge_class": "INSUFFICIENT_N"}},
            decision=decision,
            now=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
    assert p["live_armed"] is False
    assert p["n_planned"] == 0
    assert p["n_blocked"] == 1
    assert any("live_apply_not_armed" in r for r in p["plans"][0]["reasons"])


def test_armed_cf_waived_plans():
    decision = {
        "schema": "x",
        "live_apply": True,
        "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 0},
    }
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 0, "usd_spent": 0.0, "pairs": [], "events": []
    }), patch.object(shadow, "_load_json", return_value={"lots": {}}), patch.object(
        live, "_write_json"
    ):
        p = live.plan_live_steps(
            decisions=[_would()],
            board={"cf": {"n": 0, "edge_class": "INSUFFICIENT_N"}},
            decision=decision,
            cfg=shadow.load_cfg(),
            now=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
    assert p["live_armed"] is True
    assert p["n_planned"] == 1
    assert p["plans"][0]["step_usd"] == 25.0
    assert p["cf_gate"]["waived"] is True


def test_cf_waive_budget_exhausted_blocks():
    decision = {
        "schema": "x",
        "live_apply": True,
        "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 2},
    }
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 0, "usd_spent": 0.0, "pairs": [], "events": []
    }), patch.object(shadow, "_load_json", return_value={"lots": {}}), patch.object(
        live, "_write_json"
    ):
        p = live.plan_live_steps(
            decisions=[_would()],
            board={"cf": {"n": 0, "edge_class": "INSUFFICIENT_N"}},
            decision=decision,
            now=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
    assert p["n_planned"] == 0
    assert p["cf_gate"]["ok"] is False
    assert "exhausted" in p["cf_gate"]["reason"]


def test_cf_waive_require_false_needs_budget():
    decision = {"live_apply": True, "cf_bar": {"require": False, "max_waived_steps": 0}}
    g = live.cf_bar_cleared({"n": 0, "edge_class": "INSUFFICIENT_N"}, decision=decision)
    assert g["ok"] is False
    assert "max_waived_steps=0" in g["reason"]


def test_cf_bar_blocks_when_required():
    decision = {"live_apply": True, "cf_bar": {"require": True, "min_scored": 8}}
    gate = live.cf_bar_cleared(
        {"n": 0, "edge_class": "INSUFFICIENT_N"}, decision, shadow.load_cfg()
    )
    assert gate["ok"] is False
    assert "cf_n=0" in gate["reason"]


def test_kill_switch_disarms():
    with patch.object(live, "KILL_PATH") as kp:
        # use real kill check via exists mock
        pass
    decision = {"live_apply": True}
    with patch.object(live, "kill_switch_on", return_value=True):
        assert live.is_live_armed(decision) is False


def test_apply_dry_run_never_calls_buy():
    decision = {"live_apply": True, "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 0}}
    plan = {
        "plans": [
            {
                "pair": "ZEC-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "status": "planned",
                "unrealized_r": 0.02,
                "hold_hours": 5,
                "phase": 1,
                "structure_ok": True,
            }
        ]
    }
    ex = MagicMock()
    ex.shadow_mode = False
    ex.execute_buy = MagicMock(return_value={"success": True, "order_id": "x"})
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 0, "usd_spent": 0.0, "pairs": [], "events": []
    }), patch.object(live, "_write_json"), patch.object(live, "_append_crumb"):
        s = live.apply_live_steps(plan, dry_run=True, go=True, executor=ex)
    assert s["money_moved"] is False
    assert s["mode"] == "dry_run_go"
    ex.execute_buy.assert_not_called()
    assert s["results"][0].get("would_apply") is True


def test_apply_live_calls_buy_once():
    decision = {"live_apply": True, "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 0}}
    plan = {
        "plans": [
            {
                "pair": "ZEC-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "status": "planned",
                "unrealized_r": 0.02,
                "hold_hours": 5,
                "phase": 1,
                "structure_ok": True,
            }
        ]
    }
    ex = MagicMock()
    ex.shadow_mode = False
    ex.execute_buy = MagicMock(
        return_value={
            "success": True,
            "order_id": "oid-1",
            "entry_price": 50.0,
            "size": 0.5,
            "sl_attached": True,
            "execution_style": "market_ioc",
            "fill_status": "full",
        }
    )
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(
        live,
        "load_daily",
        return_value={
            "utc_day": "2026-09-19",
            "n_steps": 0,
            "usd_spent": 0.0,
            "pairs": [],
            "events": [],
        },
    ), patch.object(live, "_save_daily") as save_d, patch.object(
        live, "_write_json"
    ), patch.object(live, "_append_crumb"), patch.object(
        shadow, "_mark_open_lot_scaled"
    ) as mark, patch.object(shadow, "_load_json", return_value={"lots": {"ZEC-USD": {"scaled": True}}}), patch.object(
        shadow, "_write_json"
    ):
        s = live.apply_live_steps(plan, dry_run=False, go=True, executor=ex)
    assert s["money_moved"] is True
    assert s["n_applied"] == 1
    ex.execute_buy.assert_called_once()
    args, kwargs = ex.execute_buy.call_args
    assert args[0] == "ZEC-USD"
    assert abs(float(args[1]) - 25.0) < 1e-9
    mark.assert_called_once()
    save_d.assert_called()


def test_apply_refuses_when_not_armed_even_with_go():
    decision = {"live_apply": False, "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 0}}
    plan = {
        "plans": [
            {
                "pair": "LINK-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "status": "planned",
            }
        ]
    }
    # status planned shouldn't happen if not armed, but apply must still refuse money
    ex = MagicMock()
    ex.shadow_mode = False
    ex.execute_buy = MagicMock()
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 0, "usd_spent": 0.0, "pairs": [], "events": []
    }), patch.object(live, "_write_json"), patch.object(live, "_append_crumb"):
        s = live.apply_live_steps(plan, dry_run=False, go=True, executor=ex)
    assert s["money_moved"] is False
    assert s["live_armed"] is False
    ex.execute_buy.assert_not_called()


def test_daily_cap_blocks_second():
    decision = {
        "live_apply": True,
        "cf_bar": {"require": False, "max_waived_steps": 2, "waived_steps_used": 0},
    }
    with patch.object(live, "load_decision", return_value=decision), patch.object(
        live, "kill_switch_on", return_value=False
    ), patch.object(live, "load_daily", return_value={
        "utc_day": "2026-09-19", "n_steps": 1, "usd_spent": 25.0, "pairs": ["ZEC-USD"], "events": []
    }), patch.object(shadow, "_load_json", return_value={"lots": {}}), patch.object(
        live, "_write_json"
    ):
        p = live.plan_live_steps(
            decisions=[_would("LINK-USD")],
            board={"cf": {"n": 12, "edge_class": "ATTENTION_ONLY_scale_helps"}},
            decision=decision,
            now=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
    assert p["n_planned"] == 0
    assert any("daily_max_steps" in r for r in p["plans"][0]["reasons"])


if __name__ == "__main__":
    test_not_armed_blocks_plan()
    test_armed_cf_waived_plans()
    test_cf_waive_budget_exhausted_blocks()
    test_cf_waive_require_false_needs_budget()
    test_cf_bar_blocks_when_required()
    test_kill_switch_disarms()
    test_apply_dry_run_never_calls_buy()
    test_apply_live_calls_buy_once()
    test_apply_refuses_when_not_armed_even_with_go()
    test_daily_cap_blocks_second()
    print("ALL PASS isolation_tryout_scale_up_live")
