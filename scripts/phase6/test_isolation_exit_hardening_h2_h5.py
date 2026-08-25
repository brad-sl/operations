#!/usr/bin/env python3
"""Isolation: EXIT-H4 / H5 / H2 / H3 readiness."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def test_qty_ssot():
    from phase6.core.position_qty import (
        ensure_live_state_qty_aliases,
        normalize_position_row,
        position_qty,
        qty_map_from_live_state,
    )

    assert position_qty({"amount": 92.58}) == 92.58
    assert position_qty({"qty": 1.5}) == 1.5
    assert position_qty({"quantity": 2.0, "amount": 0}) == 2.0
    row = {"pair": "X-USD", "amount": 10.0}
    normalize_position_row(row)
    assert row["qty"] == 10.0 and row["quantity"] == 10.0

    live = {"positions": [{"pair": "LINK-USD", "amount": 92.58, "value_usd": 1000}]}
    m = qty_map_from_live_state(live)
    assert abs(m["LINK-USD"] - 92.58) < 1e-9

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "live.json"
        p.write_text(json.dumps({"positions": [{"pair": "A-USD", "amount": 3.0}]}))
        s = ensure_live_state_qty_aliases(p)
        assert s.get("updated") is True
        data = json.loads(p.read_text())
        assert data["positions"][0]["qty"] == 3.0
        assert data["positions"][0]["quantity"] == 3.0
    print("H5 qty_ssot OK")


def test_post_tp_structure_early_release_floor():
    from phase6.core import runner_capital_events as rce

    now = datetime.now(timezone.utc).timestamp()
    # elapsed 2h < floor 4h → keep
    blocks = {
        "AAA-USD": {
            "blocked": True,
            "reason": "post_tp_rebuy_block",
            "block_hours": 24.0,
            "hours_remaining": 22.0,
        }
    }
    out = rce._apply_post_tp_structure_early_release(blocks, now=now)
    assert "AAA-USD" in out, out

    # non-post-tp reason untouched
    blocks2 = {
        "BBB-USD": {
            "blocked": True,
            "reason": "post_sl_rebuy_block",
            "block_hours": 72.0,
            "hours_remaining": 1.0,
        }
    }
    out2 = rce._apply_post_tp_structure_early_release(blocks2, now=now)
    assert "BBB-USD" in out2

    # elapsed ok + ignition + structure → drop
    blocks3 = {
        "CCC-USD": {
            "blocked": True,
            "reason": "post_tp_rebuy_block",
            "block_hours": 24.0,
            "hours_remaining": 18.0,  # elapsed 6h
        }
    }
    fake_snap = MagicMock()
    fake_snap.phase = 1
    fake_struct = MagicMock()
    fake_struct.structure_ok_for_entry = True
    with patch.object(rce, "_post_tp_structure_cfg", return_value={
        "structure_aware": True,
        "early_release_phases": [1, 2],
        "min_hours_floor": 4.0,
        "require_structure_ok": True,
    }), patch(
        "phase6.core.run_phase_deploy.fetch_daily_candles_public",
        return_value=[{"c": 1}] * 30,
    ), patch(
        "phase6.core.run_phase_deploy.classify_run_phase",
        return_value=fake_snap,
    ), patch(
        "phase6.core.run_phase_deploy.load_run_phase_config",
        return_value={},
    ), patch(
        "phase6.core.run_lifecycle.classify_structure",
        return_value=fake_struct,
    ):
        out3 = rce._apply_post_tp_structure_early_release(dict(blocks3), now=now)
    assert "CCC-USD" not in out3, out3
    print("H4 post_tp structure early-release OK")


def test_h2_effective_tp_attach_gate():
    from phase6.core.shadow_tp import effective_tp_pct_for_buy

    assert (
        effective_tp_pct_for_buy(
            {"take_profit": {"mode": "live", "fixed_tp_pct": 0.06, "live_attach_on_buy": False}}
        )
        is None
    )
    assert (
        effective_tp_pct_for_buy(
            {"take_profit": {"mode": "live", "fixed_tp_pct": 0.06, "live_attach_on_buy": True}}
        )
        == 0.06
    )
    print("H2 attach gate OK (default false)")


def test_h3_hard_exit_live_when_approved_off():
    from types import SimpleNamespace
    from phase6.core.regime_cash_policy import apply_hard_exit_to_plan
    from unittest.mock import MagicMock, patch
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        logp = Path(td) / "he.json"
        with patch(
            "phase6.core.regime_cash_policy.build_hard_exit_sell_actions",
            return_value=[{"pair": "Z-USD", "action": "SELL", "usd": 100}],
        ):
            snap_m = MagicMock()
            snap_m.regime = "flat"
            snap_m.strategy_mode = "park"
            plan1 = SimpleNamespace(actions=[])
            apply_hard_exit_to_plan(
                plan1,
                snap_m,
                {"Z-USD": 200.0},
                hard_cfg={
                    "enabled": True,
                    "shadow_only": False,
                    "live_apply": True,
                    "operator_approve": True,
                    "notify_telegram": False,
                    "min_sell_usd": 25,
                },
                shadow_log_path=logp,
            )
            assert plan1.actions == [], "operator_approve must block live merge"

            plan2 = SimpleNamespace(actions=[])
            apply_hard_exit_to_plan(
                plan2,
                snap_m,
                {"Z-USD": 200.0},
                hard_cfg={
                    "enabled": True,
                    "shadow_only": False,
                    "live_apply": True,
                    "operator_approve": False,
                    "notify_telegram": False,
                    "min_sell_usd": 25,
                },
                shadow_log_path=logp,
            )
            assert any(a.get("pair") == "Z-USD" for a in plan2.actions), plan2.actions
    print("H3 hard_exit auto path ready (approve=false merges)")


def main() -> int:
    fails = []
    for fn in (
        test_qty_ssot,
        test_post_tp_structure_early_release_floor,
        test_h2_effective_tp_attach_gate,
        test_h3_hard_exit_live_when_approved_off,
    ):
        try:
            fn()
        except Exception as e:
            fails.append(f"{fn.__name__}: {e}")
            import traceback

            traceback.print_exc()
    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
