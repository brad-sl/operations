#!/usr/bin/env python3
"""Isolation: W2 shell-only 3% fuse resolver (gated; never global 8→3)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestW2Resolve(unittest.TestCase):
    def _base_policy(self, live: bool = False) -> dict:
        return {
            "status": "TEST",
            "live_apply": live,
            "w2_live_apply": live,
            "w2_sl_pct": 0.03,
            "w2_sl_min": 0.03,
            "w2_sl_max": 0.05,
            "live_default": {"stop_loss_pct": 0.08},
            "arming_rules_shadow": [
                {
                    "id": "W2_tight_unproven_shell",
                    "sl_base_pct": 0.03,
                    "sl_min_pct": 0.03,
                    "sl_max_pct": 0.05,
                    "live_apply": live,
                }
            ],
            "shell_notional_lte_usd": 30.0,
            "min_hours_held": 4.0,
            "mfe_green_pct": 0.02,
            "core_pairs": ["BTC-USD", "ETH-USD"],
        }

    def test_shadow_never_overrides(self) -> None:
        from phase6.core import sl_width_would_arm_shadow as s

        with mock.patch.object(s, "KILL") as k:
            k.is_file = lambda: False
            r = s.resolve_live_sl_pct(
                pair="ADA-USD",
                held_usd=25.0,
                role="tryout_shell",
                has_tryout_lot=True,
                mfe_pct=0.0,
                hours_held=10.0,
                graduated=False,
                policy=self._base_policy(False),
            )
        self.assertFalse(r.get("live_override"))
        self.assertAlmostEqual(float(r.get("sl_pct")), 0.08)
        self.assertTrue(r.get("would_arm_3pct"))

    def test_live_dead_shell_gets_3pct(self) -> None:
        from phase6.core import sl_width_would_arm_shadow as s

        with mock.patch.object(s, "KILL") as k:
            k.is_file = lambda: False
            r = s.resolve_live_sl_pct(
                pair="ADA-USD",
                held_usd=25.0,
                role="tryout_shell",
                has_tryout_lot=True,
                mfe_pct=0.0,
                hours_held=10.0,
                graduated=False,
                policy=self._base_policy(True),
            )
        self.assertTrue(r.get("live_override"))
        self.assertAlmostEqual(float(r.get("sl_pct")), 0.03)

    def test_live_core_stays_8(self) -> None:
        from phase6.core import sl_width_would_arm_shadow as s

        with mock.patch.object(s, "KILL") as k:
            k.is_file = lambda: False
            r = s.resolve_live_sl_pct(
                pair="BTC-USD",
                held_usd=200.0,
                role="ballast_core",
                has_tryout_lot=False,
                mfe_pct=0.05,
                hours_held=100.0,
                graduated=False,
                policy=self._base_policy(True),
            )
        self.assertFalse(r.get("live_override"))
        self.assertAlmostEqual(float(r.get("sl_pct")), 0.08)
        self.assertFalse(r.get("would_arm_3pct"))

    def test_kill_file_blocks_live(self) -> None:
        from phase6.core import sl_width_would_arm_shadow as s

        with mock.patch.object(s, "KILL") as k:
            k.is_file = lambda: True
            self.assertFalse(s.effective_w2_live(self._base_policy(True)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
