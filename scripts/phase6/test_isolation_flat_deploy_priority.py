#!/usr/bin/env python3
"""Isolation tests for flat deploy priority / ballast before shell (shadow only).

Per §D1:
- regime == "flat" or "transition"
- deploy_cap_usd (e.g. 75)
- if BTC or ETH held < 0.35 * target_w * eq AND not late_run_blocked
  → would_prefer_ballast True, reserve = min(75, gap)
- else not prefer
- late-run both blocked → shells_ok (allow shells)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SHADOW_CFG = {
    "live_apply": False,
    "shadow_only": True,
    "flat_regimes": ["flat", "transition"],
    "deploy_cap_usd": 75,
    "min_held_pct": 0.35,
    "reserve_before_shell": True,
    "late_run_block_allows_shell": True,
}

class TestFlatDeployPriority(unittest.TestCase):
    def test_empty_eth_micro_btc_flat_prefers_ballast(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        res = fdp.would_prefer_ballast_before_shell(
            regime="flat",
            deploy_cap_usd=75.0,
            btc_held=20.0,   # micro < 0.35*target
            eth_held=0.0,
            equity=2500.0,
            target_w_btc=0.18,
            target_w_eth=0.12,
            btc_late_run_blocked=False,
            eth_late_run_blocked=False,
            cfg=SHADOW_CFG,
        )
        self.assertTrue(res.get("would_prefer_ballast"))
        self.assertGreaterEqual(res.get("reserve_usd", 0), 50)  # min(75, gap)
        self.assertTrue(res.get("shadow"))
        self.assertIn("reasons", res)
        self.assertFalse(res.get("shells_ok", True))  # prefer ballast so no new shell yet?

    def test_both_filled_ge_35pct_not_prefer(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        # target_btc=0.18*2500=450, 0.35*450=157.5; held 200>157
        # eth 0.12*2500=300, 0.35*105; held 120>
        res = fdp.would_prefer_ballast_before_shell(
            regime="flat",
            deploy_cap_usd=75.0,
            btc_held=200.0,
            eth_held=120.0,
            equity=2500.0,
            target_w_btc=0.18,
            target_w_eth=0.12,
            btc_late_run_blocked=False,
            eth_late_run_blocked=False,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("would_prefer_ballast"))
        self.assertEqual(res.get("reserve_usd", 0), 0.0)
        self.assertTrue(any("both_sufficiently_held" in r or "no_gap" in r for r in res.get("reasons", [])))

    def test_late_run_both_blocked_shells_ok(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        res = fdp.would_prefer_ballast_before_shell(
            regime="flat",
            deploy_cap_usd=75.0,
            btc_held=10.0,
            eth_held=5.0,
            equity=2500.0,
            target_w_btc=0.18,
            target_w_eth=0.12,
            btc_late_run_blocked=True,
            eth_late_run_blocked=True,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("would_prefer_ballast"))  # blocked so don't reserve?
        self.assertTrue(res.get("shells_ok", False))
        self.assertTrue(any("late_run_blocked" in r for r in res.get("reasons", [])))

    def test_transition_regime_still_applies(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        res = fdp.would_prefer_ballast_before_shell(
            regime="transition",
            deploy_cap_usd=75.0,
            btc_held=30.0,
            eth_held=0.0,
            equity=2000.0,
            target_w_btc=0.20,
            target_w_eth=0.10,
            btc_late_run_blocked=False,
            eth_late_run_blocked=False,
            cfg=SHADOW_CFG,
        )
        self.assertTrue(res.get("would_prefer_ballast"))
        self.assertTrue(res.get("shadow"))

    def test_non_flat_regime_no_prefer(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        res = fdp.would_prefer_ballast_before_shell(
            regime="bull",
            deploy_cap_usd=75.0,
            btc_held=10.0,
            eth_held=0.0,
            equity=2500.0,
            target_w_btc=0.18,
            target_w_eth=0.12,
            btc_late_run_blocked=False,
            eth_late_run_blocked=False,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("would_prefer_ballast"))

    def test_config_defaults(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        cfg = fdp.load_config()
        self.assertIn("live_apply", cfg)
        self.assertEqual(cfg.get("deploy_cap_usd", 75), 75)
        self.assertEqual(cfg.get("min_held_pct"), 0.35)
        self.assertIn("flat", cfg.get("flat_regimes", ["flat", "transition"]))

    def test_live_shell_gate_blocks_when_live(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        cfg = {
            "live_apply": True,
            "shadow_only": False,
            "flat_regimes": ["flat", "transition"],
            "deploy_cap_usd": 75,
            "min_held_pct": 0.35,
            "reserve_before_shell": True,
            "late_run_block_allows_shell": True,
        }
        with mock.patch.object(fdp, "kill_file_on", return_value=False):
            g = fdp.live_shell_gate(
                regime="flat",
                deploy_cap_usd=75.0,
                btc_held=20.0,
                eth_held=0.0,
                equity=2500.0,
                target_w_btc=0.18,
                target_w_eth=0.12,
                cfg=cfg,
            )
        self.assertTrue(g.get("block_shell"))
        self.assertTrue(g.get("would_block_if_live"))

    def test_live_shell_gate_shadow_no_block(self) -> None:
        from phase6.core import flat_deploy_priority as fdp
        cfg = {
            "live_apply": False,
            "shadow_only": True,
            "flat_regimes": ["flat", "transition"],
            "deploy_cap_usd": 75,
            "min_held_pct": 0.35,
            "reserve_before_shell": True,
            "late_run_block_allows_shell": True,
        }
        g = fdp.live_shell_gate(
            regime="flat",
            deploy_cap_usd=75.0,
            btc_held=20.0,
            eth_held=0.0,
            equity=2500.0,
            target_w_btc=0.18,
            target_w_eth=0.12,
            cfg=cfg,
        )
        self.assertFalse(g.get("block_shell"))
        self.assertTrue(g.get("would_block_if_live"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
