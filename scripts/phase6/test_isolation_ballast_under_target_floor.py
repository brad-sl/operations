#!/usr/bin/env python3
"""Isolation tests for ballast under-target floor (shadow, no orders, no live_apply).

Per §C1 spec:
- pairs BTC-USD/ETH-USD + ballast_core role only
- max_step 75, respect flat cap
- min_held_pct 0.35 skip if already >=
- require stop, not over target
- forbid upnl < -0.06
- when max_add >= min_useful (default $25): already_has_max_add (no floor)
- when 0 < max_add < min_useful: residual stub → floor may inject (Brad GO A 2026-10-23)
- step = min(max_step, flat_cap, max(0, target-held))
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
    "pairs_allow": ["BTC-USD", "ETH-USD"],
    "roles_allow": ["ballast_core"],
    "max_step_usd": 75,
    "min_held_pct_of_target_to_skip": 0.35,
    "require_stop_attached": True,
    "require_not_over_target": True,
    "forbid_if_open_upnl_pct_lt": -0.06,
    "default_flat_cap_usd": 75,
    "min_useful_max_add_usd": 25.0,
}

class TestBallastUnderTargetFloor(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = None  # no temp needed for pure fn

    def test_btc_under_target_flat_maxadd0_stop_ok_allows(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertTrue(res.get("allow"))
        self.assertGreater(res.get("step_usd", 0), 0)
        self.assertIn("shadow", res)
        self.assertTrue(res.get("shadow"))
        # target_val = 0.18*2260 ≈ 406.8, gap≈351.8 but capped at min(75,75,351.8)=75
        self.assertAlmostEqual(res.get("step_usd", 0), 75.0, places=1)
        self.assertEqual(res.get("reasons"), [])

    def test_paxg_reject(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="PAXG-USD",
            role="preserve_ballast",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("pair_not_allowed" in r or "role_not_ballast" in r for r in res.get("reasons", [])))

    def test_upnl_too_negative_reject(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.08,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("upnl_below_forbid" in r for r in res.get("reasons", [])))

    def test_no_stop_reject(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=False,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("stop_required" in r for r in res.get("reasons", [])))

    def test_over_target_reject(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=500.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("over_target" in r for r in res.get("reasons", [])))

    def test_already_has_max_add_reject_no_floor(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=50.0,  # useful room (>= min_useful $25)
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("already_has_max_add" in r for r in res.get("reasons", [])))

    def test_residual_max_add_under_min_useful_allows_floor(self) -> None:
        """Brad GO A 2026-10-23: risk-math stub (~$7) must not block C2 floor."""
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=7.24,  # residual under min_move
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertTrue(res.get("allow"), res)
        self.assertAlmostEqual(float(res.get("step_usd") or 0), 75.0, places=1)
        self.assertAlmostEqual(float(res.get("residual_max_add_usd") or 0), 7.24, places=2)

    def test_apply_floor_injects_over_residual_stub(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        cfg = {
            "live_apply": True,
            "shadow_only": False,
            "pairs_allow": ["BTC-USD", "ETH-USD"],
            "roles_allow": ["ballast_core"],
            "max_step_usd": 75,
            "min_held_pct_of_target_to_skip": 0.35,
            "require_stop_attached": True,
            "require_not_over_target": True,
            "forbid_if_open_upnl_pct_lt": -0.06,
            "default_flat_cap_usd": 75,
            "min_useful_max_add_usd": 25.0,
        }
        with mock.patch.object(buf, "kill_file_on", return_value=False):
            inj = buf.apply_floor_to_max_add(
                pair="BTC-USD",
                role="ballast_core",
                held_usd=55.0,
                equity_usd=2260.0,
                target_w=0.18,
                max_add_usd=7.24,
                open_upnl_pct=-0.02,
                stop_attached=True,
                flat_cap_usd=75.0,
                min_useful_max_add_usd=25.0,
                cfg=cfg,
            )
        self.assertTrue(inj.get("injected"), inj)
        self.assertAlmostEqual(float(inj.get("max_add_after") or 0), 75.0, places=1)

    def test_min_held_pct_skip(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        # target ~406.8, 0.35*406.8~142, held 150 >= skip
        res = buf.would_allow_under_target_step(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=150.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=SHADOW_CFG,
        )
        self.assertFalse(res.get("allow"))
        self.assertTrue(any("min_held_pct_skip" in r or "already_sufficient" in r for r in res.get("reasons", [])))

    def test_step_capped_by_flat_and_max(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        res = buf.would_allow_under_target_step(
            pair="ETH-USD",
            role="ballast_core",
            held_usd=10.0,
            equity_usd=3000.0,
            target_w=0.15,
            max_add_usd=0.0,
            open_upnl_pct=-0.01,
            stop_attached=True,
            flat_cap_usd=40.0,  # flat cap smaller,
            cfg=SHADOW_CFG,
        )
        self.assertTrue(res.get("allow"))
        target_val = 0.15 * 3000
        expected = min(75, 40, max(0, target_val - 10))
        self.assertAlmostEqual(res.get("step_usd", 0), expected, places=1)

    def test_config_defaults_loaded(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        cfg = buf.load_config()
        # live_apply may be True after Brad GO reverse-stack; assert shape not OFF pin
        self.assertIn("live_apply", cfg)
        self.assertIn("BTC-USD", cfg.get("pairs_allow", []))
        self.assertEqual(cfg.get("max_step_usd"), 75)
        self.assertEqual(cfg.get("min_held_pct_of_target_to_skip"), 0.35)
        self.assertTrue(cfg.get("require_stop_attached"))
        self.assertEqual(cfg.get("forbid_if_open_upnl_pct_lt"), -0.06)

    def test_apply_floor_respects_cfg_live_flag(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        cfg = {
            "live_apply": True,
            "shadow_only": False,
            "pairs_allow": ["BTC-USD", "ETH-USD"],
            "roles_allow": ["ballast_core"],
            "max_step_usd": 75,
            "min_held_pct_of_target_to_skip": 0.35,
            "require_stop_attached": True,
            "require_not_over_target": True,
            "forbid_if_open_upnl_pct_lt": -0.06,
            "default_flat_cap_usd": 75,
        }
        with mock.patch.object(buf, "kill_file_on", return_value=False):
            inj = buf.apply_floor_to_max_add(
                pair="BTC-USD",
                role="ballast_core",
                held_usd=55.0,
                equity_usd=2260.0,
                target_w=0.18,
                max_add_usd=0.0,
                open_upnl_pct=-0.02,
                stop_attached=True,
                flat_cap_usd=75.0,
                cfg=cfg,
            )
        self.assertTrue(inj.get("injected"))
        self.assertAlmostEqual(float(inj.get("max_add_after") or 0), 75.0, places=1)

    def test_apply_floor_shadow_no_inject(self) -> None:
        from phase6.core import ballast_under_target_floor as buf
        cfg = {
            "live_apply": False,
            "shadow_only": True,
            "pairs_allow": ["BTC-USD", "ETH-USD"],
            "roles_allow": ["ballast_core"],
            "max_step_usd": 75,
            "min_held_pct_of_target_to_skip": 0.35,
            "require_stop_attached": True,
            "require_not_over_target": True,
            "forbid_if_open_upnl_pct_lt": -0.06,
            "default_flat_cap_usd": 75,
        }
        inj = buf.apply_floor_to_max_add(
            pair="BTC-USD",
            role="ballast_core",
            held_usd=55.0,
            equity_usd=2260.0,
            target_w=0.18,
            max_add_usd=0.0,
            open_upnl_pct=-0.02,
            stop_attached=True,
            flat_cap_usd=75.0,
            cfg=cfg,
        )
        self.assertFalse(inj.get("injected"))
        self.assertTrue(inj.get("would", {}).get("allow"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
