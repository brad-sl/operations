#!/usr/bin/env python3
"""Isolation: tryout fund-from-USDC planner (pure) + money-path proof grades."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_fund_from_usdc import (  # noqa: E402
    plan_fund_for_shell,
    usd_usdc_from_live_state,
)


class TestFundPlan(unittest.TestCase):
    def test_covers_hold(self):
        p = plan_fund_for_shell(shell_usd=25, usd=200, usdc=1700)
        self.assertEqual(p.action, "hold")
        self.assertEqual(p.reason, "usd_covers_shell")
        self.assertEqual(p.unwind_usd, 0.0)

    def test_thin_usd_unwinds_shortfall_only(self):
        p = plan_fund_for_shell(shell_usd=25, usd=10, usdc=1700, buffer_usd=5)
        self.assertEqual(p.action, "unwind")
        # need 30, shortfall 20
        self.assertEqual(p.unwind_usd, 20.0)
        self.assertLessEqual(p.unwind_usd, 150.0)

    def test_never_dump_all_usdc(self):
        p = plan_fund_for_shell(shell_usd=25, usd=0, usdc=2000, buffer_usd=5)
        self.assertEqual(p.action, "unwind")
        self.assertLessEqual(p.unwind_usd, 150.0)
        self.assertLess(p.unwind_usd, 500.0)

    def test_park_blocks_unwind(self):
        p = plan_fund_for_shell(
            shell_usd=25, usd=5, usdc=1700, park_or_bear=True, buffer_usd=5
        )
        self.assertIn(p.action, ("blocked", "hold"))
        self.assertEqual(p.reason, "park_or_bear_keep_usdc")
        self.assertEqual(p.unwind_usd, 0.0)

    def test_no_usdc_blocked(self):
        p = plan_fund_for_shell(shell_usd=25, usd=5, usdc=2, buffer_usd=5)
        self.assertEqual(p.action, "blocked")
        self.assertIn("usdc", p.reason)

    def test_live_state_parse(self):
        live = {
            "balances": [
                {"currency": "USD", "available": 50.5},
                {"currency": "USDC", "available": 100.0},
            ]
        }
        b = usd_usdc_from_live_state(live)
        self.assertAlmostEqual(b["usd"], 50.5)
        self.assertAlmostEqual(b["usdc"], 100.0)


class TestMoneyPathProof(unittest.TestCase):
    def test_build_proof_runs(self):
        from scripts.phase6 import run_tryout_money_path_proof as m

        # import path: load module functions
        import importlib.util

        path = ROOT / "scripts/phase6/run_tryout_money_path_proof.py"
        spec = importlib.util.spec_from_file_location("tmp_mproof", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        proof = mod.build_proof()
        self.assertEqual(proof["schema"], "tryout_money_path_proof_v1")
        self.assertIn("FUND", proof["grades"])
        self.assertIn("SL", proof["grades"])
        self.assertIn("GROW", proof["grades"])
        for leg in ("fund", "sl", "growth"):
            self.assertIn("grade", proof[leg])
            self.assertIn("plain", proof[leg])


if __name__ == "__main__":
    unittest.main(verbosity=2)
