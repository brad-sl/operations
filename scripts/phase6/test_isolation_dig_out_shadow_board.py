#!/usr/bin/env python3
"""Isolation: dig-out shadow board + SL would-arm classify. No orders."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestSlWidthWouldArm(unittest.TestCase):
    def test_w2_dead_shell_arms_3(self):
        from phase6.core.sl_width_would_arm_shadow import classify_would_arm

        r = classify_would_arm(
            pair="LINK-USD",
            held_usd=25.0,
            role="tryout_shell",
            has_tryout_lot=True,
            mfe_pct=0.005,
            hours_held=12.0,
            graduated=False,
        )
        self.assertTrue(r["would_arm_3pct"])
        self.assertFalse(r["would_arm_8pct"])
        self.assertEqual(r["rule_id"], "W2_tight_unproven_shell")

    def test_w3_green_keeps_8(self):
        from phase6.core.sl_width_would_arm_shadow import classify_would_arm

        r = classify_would_arm(
            pair="ETH-USD",
            held_usd=200.0,
            role="ballast_core",
            has_tryout_lot=False,
            mfe_pct=0.04,
            hours_held=100.0,
            graduated=False,
        )
        self.assertFalse(r["would_arm_3pct"])
        self.assertTrue(r["would_arm_8pct"])
        self.assertEqual(r["rule_id"], "W3_never_tighten_after_green")

    def test_core_default_8(self):
        from phase6.core.sl_width_would_arm_shadow import classify_would_arm

        r = classify_would_arm(
            pair="BTC-USD",
            held_usd=55.0,
            role="ballast_core",
            has_tryout_lot=False,
            mfe_pct=0.0,
            hours_held=50.0,
            graduated=False,
        )
        self.assertFalse(r["would_arm_3pct"])
        self.assertTrue(r["would_arm_8pct"])


class TestDigOutBoard(unittest.TestCase):
    def test_build_board_shadow_fields(self):
        from phase6.core import dig_out_shadow_board as dob

        matrix = {
            "rows": [
                {
                    "pair": "BTC-USD",
                    "role": "ballast_core",
                    "held_usd": 55.0,
                    "max_add_usd": 0.0,
                    "target_pair_weight": 0.18,
                    "open_upnl_usd": -1.0,
                    "block_reason": "zero_risk_budget",
                    "has_tryout_lot": False,
                },
                {
                    "pair": "ETH-USD",
                    "role": "ballast_core",
                    "held_usd": 0.0,
                    "max_add_usd": None,
                    "target_pair_weight": 0.12,
                    "open_upnl_usd": 0.0,
                    "block_reason": "flat_no_stack",
                    "has_tryout_lot": False,
                },
                {
                    "pair": "LINK-USD",
                    "role": "tryout_shell",
                    "held_usd": 25.0,
                    "max_add_usd": 0.0,
                    "target_pair_weight": 0.05,
                    "open_upnl_usd": -0.5,
                    "has_tryout_lot": True,
                },
            ],
            "add_room_meta": {"equity_usd": 2260.0},
            "regime_sheet": {"live_regime": "flat"},
        }
        regime = {"regime": "flat", "rebalance_cap_usd": 75.0}
        live = {"total_usd": 2260.0}
        disc = {"live_apply": True, "last_triple": {"action": "STAND_DOWN"}}

        def fake_load(path: Path):
            name = path.name
            if "membership_sizing" in name:
                return matrix
            if "regime_cash" in name:
                return regime
            if "phase6_live" in name:
                return live
            if "tryout_decision_discipline" in name:
                return disc
            return {}

        with mock.patch.object(dob, "_load", side_effect=fake_load):
            with mock.patch.object(dob, "TRIPLES", Path("/tmp/no_triples_xyz")):
                board = dob.build_board()

        self.assertFalse(board.get("live_apply"))
        self.assertEqual(board.get("schema"), "dig_out_shadow_board_v1")
        c1 = board["c1_under_target_floor"]
        self.assertGreaterEqual(c1["n_allow"], 1)
        d1 = board["d1_flat_priority"]
        self.assertTrue(d1.get("would_prefer_ballast") or d1.get("shadow"))
        self.assertIn("do_not", board)
        self.assertIn("global_stop_8_to_3", board["do_not"])


if __name__ == "__main__":
    unittest.main()
