#!/usr/bin/env python3
"""Isolation: PC-02 exit stack proof (inventory, banks, go/no-go)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.exit_stack_proof import (
    build_exit_stack_proof,
    classify_exit_reason,
    decide_go_nogo,
    inventory_exit_layers,
    score_window,
    write_artifacts,
)


def _row(side, reason, pnl, days_ago, pair="ETH-USD"):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "side": side,
        "reason": reason,
        "exit_reason": reason,
        "pnl": pnl,
        "pair": pair,
        "timestamp": ts,
    }


class TestExitStackProofPC02(unittest.TestCase):
    def test_classify_buckets(self):
        self.assertEqual(classify_exit_reason({"reason": "stop_loss_exchange"}), "sl_exchange")
        self.assertEqual(classify_exit_reason({"reason": "take_profit_trail"}), "tp_profit")
        self.assertEqual(classify_exit_reason({"reason": "lifecycle_dual_peak:x"}), "dual_peak")
        self.assertEqual(classify_exit_reason({"reason": ""}), "blank_untagged")
        self.assertEqual(classify_exit_reason({"reason": "operator_trim_x"}), "operator_manual")

    def test_window_tp_vs_sl_banks(self):
        rows = [
            _row("SELL", "stop_loss_exchange", -3.0, 1),
            _row("SELL", "stop_loss_exchange", -2.0, 2),
            _row("SELL", "take_profit_fixed_tp", 4.5, 3),
            _row("SELL", "rotation_exchange", 0.0, 1),
            _row("BUY", "signal", 0.0, 1),
            _row("SELL", "stop_loss_exchange", -1.0, 40),  # outside 7d
        ]
        w7 = score_window(rows, days=7)
        self.assertEqual(w7.n_sell, 4)
        self.assertEqual(w7.by_bucket.get("sl_exchange"), 2)
        self.assertEqual(w7.by_bucket.get("tp_profit"), 1)
        self.assertAlmostEqual(w7.sl_bank_usd, -5.0)
        self.assertAlmostEqual(w7.tp_bank_usd, 4.5)
        self.assertEqual(w7.tp_vs_sl_count, "1:2")

    def test_inventory_respects_configs(self):
        layers = inventory_exit_layers(
            exit_cfg={
                "take_profit": {"mode": "live", "live_market_exit": True, "live_attach_on_buy": False},
                "promotion": {"auto_promote": False},
            },
            regime_policy={
                "hard_exit": {
                    "enabled": True,
                    "shadow_only": True,
                    "live_apply": False,
                    "operator_approve": True,
                    "cautious_flat": {"enabled": True},
                }
            },
            trading_cfg={"run_lifecycle": {"dual_peak_exit": {"enabled": True, "mode": "live"}}},
            regime_exit_map={"live_apply": False},
        )
        by = {L["layer"]: L for L in layers}
        self.assertTrue(by["take_profit_trail_fixed"]["live_orders"])
        self.assertFalse(by["take_profit_trail_fixed"]["live_attach_on_buy"])
        self.assertFalse(by["regime_exit_map"]["live_apply"])
        self.assertEqual(by["stop_loss_exchange"]["state"], "live")

    def test_hard_exit_global_nogo(self):
        layers = inventory_exit_layers(
            exit_cfg={"take_profit": {"mode": "live", "live_market_exit": True}, "promotion": {"auto_promote": False}},
            regime_policy={
                "hard_exit": {
                    "enabled": True,
                    "shadow_only": True,
                    "live_apply": False,
                    "operator_approve": True,
                    "cautious_flat": {"enabled": True},
                }
            },
            trading_cfg={},
            regime_exit_map={"live_apply": False},
        )
        rows = [_row("SELL", "stop_loss_exchange", -2.0, i) for i in range(1, 12)]
        rows += [_row("SELL", "take_profit_trail", 1.0, 2)]
        w7 = score_window(rows, days=7)
        w30 = score_window(rows, days=30)
        from phase6.core.exit_stack_proof import disposition_honesty

        hon = disposition_honesty({"7d": w7, "30d": w30})
        verdict = decide_go_nogo(layers, {"7d": w7, "30d": w30}, hon)
        self.assertFalse(verdict["decisions"]["hard_exit_global_auto"]["go"])
        self.assertTrue(verdict["brad_required_for_any_live_flip"])
        self.assertIn("NO-GO", verdict["decisions"]["hard_exit_global_auto"]["decision"])

    def test_blank_tag_honesty_flag(self):
        rows = [_row("SELL", "", 0.0, 1) for _ in range(6)] + [_row("SELL", "stop_loss_exchange", -1.0, 1)]
        payload = build_exit_stack_proof(
            rows=rows,
            exit_cfg={"take_profit": {"mode": "shadow"}, "promotion": {"auto_promote": False}},
            regime_policy={"hard_exit": {"operator_approve": True, "shadow_only": True, "live_apply": False}},
            trading_cfg={},
            regime_exit_map={"live_apply": False},
            write=False,
        )
        self.assertFalse(payload["disposition_honesty"]["ok"])
        self.assertEqual(payload["go_nogo"]["decisions"]["disposition_tags"]["decision"], "FIX_FIRST")

    def test_write_artifacts(self):
        payload = build_exit_stack_proof(
            rows=[_row("SELL", "take_profit_fixed_tp", 2.0, 1)],
            exit_cfg={"take_profit": {"mode": "live", "live_market_exit": True}, "promotion": {"auto_promote": False}},
            regime_policy={"hard_exit": {"operator_approve": True, "shadow_only": True, "live_apply": False}},
            trading_cfg={},
            regime_exit_map={},
            write=False,
        )
        with tempfile.TemporaryDirectory() as td:
            jp = Path(td) / "e.json"
            mp = Path(td) / "e.md"
            write_artifacts(payload, state_path=jp, report_path=mp)
            self.assertEqual(json.loads(jp.read_text())["schema"], "exit_stack_proof_v1")
            self.assertIn("Exit stack proof", mp.read_text())


if __name__ == "__main__":
    unittest.main()
