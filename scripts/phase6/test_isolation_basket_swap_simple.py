#!/usr/bin/env python3
"""Isolation tests for scripts/phase6/basket_swap.py (no live writes)."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location(
    "basket_swap_mod", ROOT / "scripts" / "phase6" / "basket_swap.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class TestBasketSwapSimple(unittest.TestCase):
    def test_norm_pair(self) -> None:
        self.assertEqual(mod._norm_pair("near"), "NEAR-USD")
        self.assertEqual(mod._norm_pair("HYPE-USD"), "HYPE-USD")
        self.assertEqual(mod._norm_pair("btc"), "BTC-USD")

    def test_dual_agree_this_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "dual.json"
            p.write_text(
                json.dumps(
                    {
                        "ts": "t",
                        "this_run": {
                            "remove": "NEAR-USD",
                            "add": "HYPE-USD",
                            "agreed": True,
                        },
                        "agree_arms": ["anti_pump", "risk_adj_mom"],
                        "new_agreements": [
                            {
                                "remove": "NEAR-USD",
                                "add": "HYPE-USD",
                                "reason": "dual_agree test",
                            }
                        ],
                    }
                )
            )
            with mock.patch.object(mod, "DUAL_AGREE_LATEST", p), mock.patch.object(
                mod, "DUAL_AGREE_ARM", Path(td) / "missing.json"
            ):
                got = mod._dual_agree_swap()
            self.assertIsNotNone(got)
            rem, add, meta = got  # type: ignore[misc]
            self.assertEqual(rem, "NEAR-USD")
            self.assertEqual(add, "HYPE-USD")
            self.assertEqual(meta.get("source"), "dual_agree.this_run")

    def test_preflight_blocks_sticky_and_held(self) -> None:
        with mock.patch.object(mod, "_pairs", return_value=["BTC-USD", "NEAR-USD", "LINK-USD"]):
            with mock.patch.object(
                mod, "_holdings", return_value={"NEAR-USD": 0.0, "BTC-USD": 100.0}
            ):
                with mock.patch.object(mod, "_decision_live_swaps", return_value=False):
                    pf = mod._preflight("BTC-USD", "HYPE-USD", 40.0)
        self.assertFalse(pf["ok"])
        self.assertTrue(any("sticky" in b for b in pf["blockers"]))

    def test_main_dry_run_explicit_no_promote_write(self) -> None:
        """--go absent must call promote with dry_run=True."""
        calls = {}

        def fake_promote(rem, add, **kw):
            calls["kw"] = kw
            calls["rem"] = rem
            calls["add"] = add
            return 0, "DRY RUN — config not written, metrics not recorded."

        with mock.patch.object(mod, "_dual_agree_swap", return_value=None):
            with mock.patch.object(mod, "_run_promote", side_effect=fake_promote):
                with mock.patch.object(
                    mod,
                    "_preflight",
                    return_value={
                        "remove": "NEAR-USD",
                        "add": "HYPE-USD",
                        "before": ["NEAR-USD"],
                        "after": ["HYPE-USD"],
                        "remove_held_usd": 0.0,
                        "blockers": [],
                        "notes": [],
                        "novelty": {"blocked": False},
                        "live_membership_swaps": False,
                        "ok": True,
                    },
                ):
                    with mock.patch.object(
                        mod, "_pairs", return_value=["NEAR-USD", "LINK-USD"]
                    ):
                        with mock.patch.object(mod, "_decision_live_swaps", return_value=False):
                            with mock.patch.object(mod, "RECEIPT", Path("/tmp/basket_swap_test_receipt.json")):
                                rc = mod.main(["NEAR", "HYPE"])
        self.assertEqual(rc, 0)
        self.assertTrue(calls["kw"]["dry_run"])
        self.assertEqual(calls["rem"], "NEAR-USD")
        self.assertEqual(calls["add"], "HYPE-USD")

    def test_main_go_requires_novelty_override_when_blocked(self) -> None:
        with mock.patch.object(
            mod,
            "_preflight",
            return_value={
                "remove": "NEAR-USD",
                "add": "HYPE-USD",
                "before": ["NEAR-USD"],
                "after": ["HYPE-USD"],
                "remove_held_usd": 0.0,
                "blockers": [],
                "notes": ["novelty_blocks"],
                "novelty": {"blocked": True, "class_": "novelty_restricted"},
                "live_membership_swaps": False,
                "ok": True,
            },
        ):
            with mock.patch.object(mod, "_run_promote") as rp:
                rc = mod.main(["NEAR-USD", "HYPE-USD", "--go"])
                rp.assert_not_called()
        self.assertEqual(rc, 7)


if __name__ == "__main__":
    unittest.main()
