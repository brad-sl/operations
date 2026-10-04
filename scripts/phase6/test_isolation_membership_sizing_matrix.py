#!/usr/bin/env python3
"""Isolation tests: membership sizing matrix SSOT (no network / no orders)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestMembershipSizingMatrix(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_btc_sticky_not_kindling(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        law = msm.load_config().get("role_law") or {}
        role = msm.resolve_role(
            "BTC-USD",
            class_="sticky_core",
            held_usd=56.0,
            has_tryout_lot=False,
            role_law=law,
        )
        self.assertEqual(role, "ballast_core")
        rl = msm.role_law_for(role, law)
        self.assertEqual(rl.get("scale_path"), "add_risk_pyramid")
        self.assertFalse(rl.get("can_eject_scale_window"))
        self.assertFalse(rl.get("kindling_eligible"))
        self.assertEqual(rl.get("membership_remove"), "never")

    def test_paxg_preserve_no_kindling(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        law = msm.load_config().get("role_law") or {}
        role = msm.resolve_role(
            "PAXG-USD",
            class_="sticky_core",
            held_usd=78.0,
            has_tryout_lot=False,
            role_law=law,
        )
        self.assertEqual(role, "preserve_ballast")
        rl = msm.role_law_for(role, law)
        self.assertEqual(rl.get("scale_path"), "none")
        self.assertFalse(rl.get("kindling_eligible"))

    def test_tryout_shell_kindling_ejectable(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        law = msm.load_config().get("role_law") or {}
        role = msm.resolve_role(
            "SOL-USD",
            class_="liquid_core",
            held_usd=25.0,
            has_tryout_lot=True,
            role_law=law,
        )
        self.assertEqual(role, "tryout_shell")
        rl = msm.role_law_for(role, law)
        self.assertEqual(rl.get("scale_path"), "kindling_once")
        self.assertTrue(rl.get("can_eject_scale_window"))
        self.assertTrue(rl.get("kindling_eligible"))
        self.assertEqual(rl.get("membership_remove"), "dust_only")

    def test_inconsistency_ballast_kindling_flagged(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        row = {
            "role": "ballast_core",
            "scale_path_law": "kindling_once",
            "class": "sticky_core",
            "can_eject_scale_window": True,
            "first_fill_haircut": False,
            "kindling_scale_path": "open",
        }
        bad = msm.check_inconsistencies(row)
        self.assertIn("sticky_or_ballast_must_not_kindling", bad)
        self.assertIn("kindling_requires_non_ballast", bad)
        self.assertIn("scale_window_eject_false_for_ballast", bad)

    def test_filter_and_pair_card(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        fake = {
            "rows": [
                {
                    "pair": "BTC-USD",
                    "class": "sticky_core",
                    "role": "ballast_core",
                    "scale_path_law": "add_risk_pyramid",
                    "held_usd": 56.0,
                    "max_add_usd": 0.0,
                    "block_reason": "cash_slice",
                    "block_max": True,
                    "in_basket": True,
                    "inconsistencies": [],
                    "pyramid_allowed": True,
                    "membership_remove": "never",
                    "can_eject_scale_window": False,
                    "first_fill_haircut": False,
                    "budgets": {},
                },
                {
                    "pair": "SOL-USD",
                    "class": "liquid_core",
                    "role": "tryout_shell",
                    "scale_path_law": "kindling_once",
                    "held_usd": 25.0,
                    "max_add_usd": None,
                    "block_reason": "flat_no_stack",
                    "block_max": False,
                    "in_basket": True,
                    "inconsistencies": [],
                    "pyramid_allowed": True,
                    "membership_remove": "dust_only",
                    "can_eject_scale_window": True,
                    "first_fill_haircut": True,
                    "budgets": {},
                },
            ],
            "regime_sheet": {"live_add_risk": {"allow_pyramid": True}},
            "notation": {},
        }
        blocked = msm.filter_rows(fake, block_max=True)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["pair"], "BTC-USD")
        card = msm.pair_card("BTC-USD", fake)
        self.assertTrue(card["found"])
        self.assertIn("add_risk_pyramid", card["plain_english"])
        self.assertIn("Factor add-risk", card["how_it_scales"])

    def test_regime_sheet_has_rows(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        sheet = msm.load_regime_sheet()
        self.assertIn("rows", sheet)
        self.assertGreaterEqual(len(sheet["rows"]), 4)
        names = {r["regime"] for r in sheet["rows"]}
        self.assertIn("flat", names)
        self.assertIn("bull", names)

    def test_build_matrix_smoke_mocked(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        fake_room = {
            "enabled": True,
            "regime": "flat",
            "equity_usd": 2300.0,
            "cash_usd": 1800.0,
            "min_move_usd": 25.0,
            "target_pair_weight": 0.18,
            "by_pair": {
                "BTC-USD": {
                    "position_usd": 56.0,
                    "max_add_usd": 0.0,
                    "block_max": True,
                    "detail_reason": "capped_to_zero",
                    "budgets": {"cash_slice": 0.0, "profit": 0.04, "heat": 23.0},
                    "weight_pct": 2.4,
                    "open_upnl_usd": 0.16,
                    "target_pair_weight": 0.18,
                },
                "SOL-USD": {
                    "position_usd": 25.0,
                    "max_add_usd": 0.0,
                    "block_max": True,
                    "detail_reason": "capped_to_zero",
                    "budgets": {"cash_slice": 0.0},
                    "weight_pct": 1.1,
                    "open_upnl_usd": 0.04,
                },
            },
            "max_blocked_pairs": ["BTC-USD", "SOL-USD"],
        }

        with mock.patch.object(
            msm, "load_add_room_by_pair_for_dashboard", create=True
        ), mock.patch(
            "phase6.core.add_risk_sizer.load_add_room_by_pair_for_dashboard",
            return_value=fake_room,
        ), mock.patch.object(
            msm,
            "_class_for_pair",
            side_effect=lambda p: {
                "BTC-USD": {"class": "sticky_core", "blocked": False, "reasons": []},
                "ETH-USD": {"class": "sticky_core", "blocked": False, "reasons": []},
                "SOL-USD": {"class": "liquid_core", "blocked": False, "reasons": []},
            }.get(
                p,
                {"class": "liquid_core", "blocked": False, "reasons": []},
            ),
        ), mock.patch.object(
            msm,
            "_open_tryout_lots",
            return_value={"SOL-USD": {"pair": "SOL-USD", "status": "open"}},
        ), mock.patch(
            "phase6.core.paths.load_trading_basket",
            return_value=["BTC-USD", "ETH-USD", "SOL-USD"],
        ), mock.patch.object(
            msm, "LATEST_PATH", self.td / "msm_latest.json"
        ):
            out = msm.build_matrix(persist=True)
        self.assertEqual(out.get("schema"), msm.SCHEMA)
        self.assertGreaterEqual(len(out.get("rows") or []), 2)
        by = {r["pair"]: r for r in out["rows"]}
        self.assertEqual(by["BTC-USD"]["role"], "ballast_core")
        self.assertEqual(by["BTC-USD"]["scale_path_law"], "add_risk_pyramid")
        self.assertFalse(by["BTC-USD"]["can_eject_scale_window"])
        self.assertEqual(by["SOL-USD"]["role"], "tryout_shell")
        self.assertEqual(by["SOL-USD"]["scale_path_law"], "kindling_once")
        self.assertTrue(by["SOL-USD"]["can_eject_scale_window"])
        self.assertEqual(out.get("inconsistencies") or [], [])
        self.assertTrue((self.td / "msm_latest.json").is_file())

    def test_binding_budget_prefers_zero_cash(self) -> None:
        from phase6.core import membership_sizing_matrix as msm

        b = msm._binding_budget(
            {"cash_slice": 0.0, "profit": 0.1, "heat": 20.0}, 0.0
        )
        self.assertEqual(b, "cash_slice")


if __name__ == "__main__":
    unittest.main()
