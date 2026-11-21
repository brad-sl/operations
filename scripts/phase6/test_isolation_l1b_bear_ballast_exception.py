#!/usr/bin/env python3
"""Isolation: L1b bear ballast exception — park + C2 seed money path (no exchange)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import l1b_bear_ballast_exception as l1b  # noqa: E402
from phase6.core.c2_ballast_seeder import propose_seed_actions  # noqa: E402
from phase6.core.regime_cash_policy import (  # noqa: E402
    filter_trade_plan_regime_cash,
    resolve_regime_cash,
)
from phase6.core.test_isolation_regime_cash_policy import _pol_no_recovery  # noqa: E402


@dataclass
class FakePlan:
    actions: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


class TestL1bCore(unittest.TestCase):
    def test_clip_bounds(self):
        self.assertEqual(l1b.clip_usd({"clip_usd": 35, "hard_max_usd": 75}), 35.0)
        self.assertEqual(l1b.clip_usd({"clip_usd": 10, "hard_max_usd": 75}), 25.0)
        self.assertEqual(l1b.clip_usd({"clip_usd": 100, "hard_max_usd": 75}), 75.0)

    def test_effective_flat_cap_l1b_vs_park(self):
        with mock.patch.object(l1b, "is_live", return_value=True):
            self.assertEqual(l1b.effective_flat_cap_for_c2(0.0), 35.0)
            self.assertEqual(l1b.effective_flat_cap_for_c2(40.0), 40.0)
        with mock.patch.object(l1b, "is_live", return_value=False):
            self.assertEqual(l1b.effective_flat_cap_for_c2(0.0), 0.0)

    def test_c2_seed_step_cap_starved_without_l1b(self):
        with mock.patch.object(l1b, "is_live", return_value=False):
            self.assertEqual(l1b.c2_seed_step_cap(35.0, 0.0), 0.0)
        with mock.patch.object(l1b, "is_live", return_value=True):
            self.assertEqual(l1b.c2_seed_step_cap(75.0, 0.0), 35.0)
            self.assertEqual(l1b.c2_seed_step_cap(20.0, 0.0), 20.0)


class TestL1bMoneyPath(unittest.TestCase):
    def test_propose_seed_uses_l1b_clip_under_zero_regime_cap(self):
        """Simulate park status $0 via patched _equity_and_cap path."""
        from phase6.core import c2_ballast_seeder as seeder

        with mock.patch.object(l1b, "is_live", return_value=True), mock.patch.object(
            l1b, "clip_usd", return_value=35.0
        ), mock.patch.object(seeder, "_equity_and_cap", return_value=(2200.0, 35.0)):
            r = propose_seed_actions(
                current_allocs={"BTC-USD": 0.0, "PAXG-USD": 75.0},
                cash_usd=2000.0,
                runner=None,
                cfg={
                    "live_apply": True,
                    "shadow_only": False,
                    "require_c2_live": False,
                    "pairs_prefer": ["BTC-USD", "ETH-USD"],
                    "role": "ballast_core",
                    "default_target_w": 0.18,
                    "default_flat_cap_usd": 75.0,
                    "max_actions_per_plan": 1,
                    "tag_reason": "c2_ballast_floor",
                },
            )
        self.assertTrue(r["actions"], r)
        self.assertEqual(r["actions"][0]["pair"], "BTC-USD")
        self.assertGreaterEqual(r["actions"][0]["usd"], 25.0)
        self.assertLessEqual(r["actions"][0]["usd"], 35.0 + 1e-6)

    def test_regime_park_blocks_c2_without_l1b(self):
        pol = _pol_no_recovery()
        snap = resolve_regime_cash(
            policy=pol,
            detection={"regime": "bear", "confidence": 1.0, "btc_return_pct": -25.0},
        )
        self.assertTrue(
            snap.strategy_mode == "usdc_park" or snap.allow_new_buys is False
        )
        plan = FakePlan(
            actions=[
                {
                    "pair": "BTC-USD",
                    "action": "BUY",
                    "usd": 35.0,
                    "reason": "c2_ballast_floor",
                    "c2_ballast_floor": True,
                    "c2_seeder": True,
                    "source": "c2_ballast_seeder",
                }
            ]
        )
        with mock.patch.object(l1b, "is_live", return_value=False):
            out = filter_trade_plan_regime_cash(
                plan,
                snap=snap,
                policy=pol,
                held_pairs=set(),
                enforce=True,
            )
        buys = [
            a
            for a in out.actions
            if str(a.get("action") or "").upper() == "BUY" and "BTC" in str(a.get("pair"))
        ]
        self.assertEqual(buys, [], f"expected park block, got {out.actions}")

    def test_regime_park_passes_c2_with_l1b(self):
        pol = _pol_no_recovery()
        snap = resolve_regime_cash(
            policy=pol,
            detection={"regime": "bear", "confidence": 1.0, "btc_return_pct": -25.0},
        )
        plan = FakePlan(
            actions=[
                {
                    "pair": "BTC-USD",
                    "action": "BUY",
                    "usd": 75.0,
                    "reason": "c2_ballast_floor",
                    "c2_ballast_floor": True,
                    "c2_seeder": True,
                    "source": "c2_ballast_seeder",
                },
                {
                    "pair": "SOL-USD",
                    "action": "BUY",
                    "usd": 25.0,
                    "reason": "tryout",
                },
            ]
        )
        with mock.patch.object(l1b, "is_live", return_value=True), mock.patch.object(
            l1b, "clip_usd", return_value=35.0
        ):
            out = filter_trade_plan_regime_cash(
                plan,
                snap=snap,
                policy=pol,
                held_pairs=set(),
                enforce=True,
            )
        btc = [
            a
            for a in out.actions
            if str(a.get("action") or "").upper() == "BUY"
            and str(a.get("pair") or "").upper().startswith("BTC")
        ]
        sol = [
            a
            for a in out.actions
            if str(a.get("action") or "").upper() == "BUY" and "SOL" in str(a.get("pair") or "")
        ]
        self.assertEqual(len(btc), 1, out.actions)
        self.assertTrue(btc[0].get("regime_cash_c2_seed_pass"))
        self.assertTrue(btc[0].get("l1b_bear_ballast_pass"))
        self.assertLessEqual(float(btc[0]["usd"]), 35.0 + 1e-6)
        self.assertEqual(sol, [], "shell must stay blocked under park")

    def test_flag_files_control_is_live(self):
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "LIVE"
            kill = Path(td) / "KILL"
            with mock.patch.object(l1b, "LIVE_FLAG", live), mock.patch.object(
                l1b, "KILL_PATH", kill
            ):
                self.assertFalse(l1b.is_live())
                live.write_text("on\n")
                self.assertTrue(l1b.is_live())
                kill.write_text("off\n")
                self.assertFalse(l1b.is_live())
                kill.unlink()
                l1b.clear_live_on_trip(reason="test")
                self.assertFalse(live.is_file())
                self.assertTrue(kill.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
