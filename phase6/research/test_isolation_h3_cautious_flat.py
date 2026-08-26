#!/usr/bin/env python3
"""Isolation: EXIT-H3 cautious flat gates + auto-merge path."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import (  # noqa: E402
    apply_hard_exit_to_plan,
    evaluate_cautious_hard_gates,
)


def test_gates_require_cross_hold_green() -> None:
    ok = evaluate_cautious_hard_gates(
        "SOL-USD",
        regime="flat",
        rsi=70.0,
        overbought=65.0,
        mark_r=0.02,
        hold_hours=48.0,
        prev_rsi=60.0,
        cfg={
            "enabled": True,
            "auto_apply_regimes": ["flat"],
            "min_hold_hours": 24,
            "require_rsi_cross": True,
            "min_mark_r": 0.0,
        },
    )
    assert ok["ok"] is True
    assert ok["auto_regime"] is True

    day0 = evaluate_cautious_hard_gates(
        "SOL-USD",
        regime="flat",
        rsi=70.0,
        overbought=65.0,
        mark_r=0.02,
        hold_hours=2.0,
        prev_rsi=60.0,
        cfg={
            "enabled": True,
            "auto_apply_regimes": ["flat"],
            "min_hold_hours": 24,
            "require_rsi_cross": True,
            "min_mark_r": 0.0,
        },
    )
    assert day0["ok"] is False
    assert any("hold" in x for x in day0["reasons_fail"])

    red = evaluate_cautious_hard_gates(
        "SOL-USD",
        regime="flat",
        rsi=70.0,
        overbought=65.0,
        mark_r=-0.05,
        hold_hours=48.0,
        prev_rsi=60.0,
        cfg={
            "enabled": True,
            "auto_apply_regimes": ["flat"],
            "min_hold_hours": 24,
            "require_rsi_cross": True,
            "min_mark_r": 0.0,
        },
    )
    assert red["ok"] is False

    no_cross = evaluate_cautious_hard_gates(
        "SOL-USD",
        regime="flat",
        rsi=70.0,
        overbought=65.0,
        mark_r=0.02,
        hold_hours=48.0,
        prev_rsi=66.0,  # already overbought
        cfg={
            "enabled": True,
            "auto_apply_regimes": ["flat"],
            "min_hold_hours": 24,
            "require_rsi_cross": True,
            "min_mark_r": 0.0,
        },
    )
    assert no_cross["ok"] is False


def test_flat_auto_merges_when_gates_pass_operator_still_true() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        shadow = td_path / "shadow.json"
        mem = td_path / "rsi_mem.json"
        # Seed prev RSI below threshold
        mem.write_text(
            '{"schema":"hard_exit_rsi_memory_v1","pairs":{"Z-USD":{"rsi":60.0}}}',
            encoding="utf-8",
        )
        snap = MagicMock()
        snap.regime = "flat"
        snap.strategy_mode = "deploy"
        snap.exit = {"overbought_rsi": 65.0, "max_sentiment_hold": -0.15}

        plan = SimpleNamespace(actions=[])
        with patch(
            "phase6.core.regime_cash_policy.prefer_exit",
            return_value=SimpleNamespace(
                pair="Z-USD",
                allowed=False,
                reasons=["rsi_overbought 70>=65"],
                sentiment=0.1,
                rsi=70.0,
            ),
        ):
            apply_hard_exit_to_plan(
                plan,
                snap,
                {"Z-USD": 200.0},
                rsi_values={"Z-USD": 70.0},
                hard_cfg={
                    "enabled": True,
                    "shadow_only": True,
                    "live_apply": False,
                    "operator_approve": True,
                    "notify_telegram": False,
                    "min_sell_usd": 25,
                    "cautious_flat": {
                        "enabled": True,
                        "auto_apply_regimes": ["flat"],
                        "min_hold_hours": 24,
                        "require_rsi_cross": True,
                        "min_mark_r": 0.0,
                    },
                },
                shadow_log_path=shadow,
                position_meta={
                    "Z-USD": {
                        "entry_price": 100.0,
                        "current_price": 105.0,
                        "unrealized_pnl_pct": 0.05,
                        "opened_at": "2026-08-01T00:00:00+00:00",
                    }
                },
                rsi_memory_path=mem,
            )
        assert any(a.get("pair") == "Z-USD" for a in plan.actions), plan.actions
        assert any(
            a.get("reason") == "regime_hard_exit_cautious_flat" for a in plan.actions
        ), plan.actions


def test_bear_does_not_auto_even_with_gates() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        shadow = td_path / "shadow.json"
        mem = td_path / "rsi_mem.json"
        mem.write_text(
            '{"schema":"hard_exit_rsi_memory_v1","pairs":{"Z-USD":{"rsi":50.0}}}',
            encoding="utf-8",
        )
        snap = MagicMock()
        snap.regime = "bear"
        snap.strategy_mode = "usdc_park"
        snap.exit = {"overbought_rsi": 60.0, "max_sentiment_hold": 0.0}
        plan = SimpleNamespace(actions=[])
        with patch(
            "phase6.core.regime_cash_policy.prefer_exit",
            return_value=SimpleNamespace(
                pair="Z-USD",
                allowed=False,
                reasons=["rsi_overbought 70>=60"],
                sentiment=0.0,
                rsi=70.0,
            ),
        ):
            apply_hard_exit_to_plan(
                plan,
                snap,
                {"Z-USD": 200.0},
                rsi_values={"Z-USD": 70.0},
                hard_cfg={
                    "enabled": True,
                    "shadow_only": True,
                    "live_apply": False,
                    "operator_approve": True,
                    "notify_telegram": False,
                    "min_sell_usd": 25,
                    "cautious_flat": {
                        "enabled": True,
                        "auto_apply_regimes": ["flat"],
                        "min_hold_hours": 24,
                        "require_rsi_cross": True,
                        "min_mark_r": 0.0,
                    },
                },
                shadow_log_path=shadow,
                position_meta={
                    "Z-USD": {
                        "entry_price": 100.0,
                        "current_price": 110.0,
                        "unrealized_pnl_pct": 0.1,
                        "opened_at": "2026-08-01T00:00:00+00:00",
                    }
                },
                rsi_memory_path=mem,
            )
        assert plan.actions == [], plan.actions


def main() -> int:
    test_gates_require_cross_hold_green()
    test_flat_auto_merges_when_gates_pass_operator_still_true()
    test_bear_does_not_auto_even_with_gates()
    print("h3_cautious_flat isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
