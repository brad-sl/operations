#!/usr/bin/env python3
"""Isolation: preferred-arm auto membership gates (no live config writes)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import preferred_arm_auto_membership as m  # noqa: E402


def _bundle_pref_ok(arm="rel_btc_stable", rem="OLD-USD", add="NEW-USD", ok=True):
    return {
        "cf": {"decide": {"status": "keep_shadow"}},
        "dual_agree": {"this_run": {"agreed": False}, "new_agreements": []},
        "arms_prop": {
            "written": [
                {
                    "arm": arm,
                    "remove": rem,
                    "add": add,
                    "membership_potential_ok": ok,
                    "membership_potential": {"ok": ok},
                    "add_score": 1.0,
                    "remove_held_usd": 0.0,
                    "reason": "test",
                }
            ]
        },
    }


class TestPreferredArmAuto(unittest.TestCase):
    def test_extract_only_preferred_ok(self):
        b = _bundle_pref_ok()
        b["arms_prop"]["written"].append(
            {
                "arm": "anti_pump",
                "remove": "X-USD",
                "add": "Y-USD",
                "membership_potential_ok": True,
            }
        )
        got = m.extract_preferred_ok_writes(b, preferred="rel_btc_stable")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["add"], "NEW-USD")

    def test_extract_skips_membership_fail(self):
        b = _bundle_pref_ok(ok=False)
        self.assertEqual(m.extract_preferred_ok_writes(b, preferred="rel_btc_stable"), [])

    def test_kill_skips(self):
        with tempfile.TemporaryDirectory() as td:
            kill = Path(td) / "KILL"
            kill.write_text("x")
            with patch.object(m, "KILL", kill), patch.object(
                m, "DECISION", Path(td) / "dec.json"
            ), patch.object(m, "RECEIPT", Path(td) / "r.json"), patch.object(
                m, "CRUMBS", Path(td) / "c.jsonl"
            ):
                (Path(td) / "dec.json").write_text(
                    json.dumps(
                        {
                            "preferred_arm": "rel_btc_stable",
                            "preferred_arm_auto_membership": {"enabled": True},
                        }
                    )
                )
                r = m.try_auto_from_bundle(_bundle_pref_ok(), dry_run=True)
                self.assertEqual(r["status"], "skipped")
                self.assertEqual(r["reason"], "kill_switch_file")

    def test_disabled_skips(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(m, "KILL", Path(td) / "nope"), patch.object(
                m, "DECISION", Path(td) / "dec.json"
            ), patch.object(m, "RECEIPT", Path(td) / "r.json"), patch.object(
                m, "CRUMBS", Path(td) / "c.jsonl"
            ):
                (Path(td) / "dec.json").write_text(
                    json.dumps(
                        {
                            "preferred_arm": "rel_btc_stable",
                            "preferred_arm_auto_membership": {"enabled": False},
                        }
                    )
                )
                r = m.try_auto_from_bundle(_bundle_pref_ok(), dry_run=True)
                self.assertEqual(r["status"], "skipped")
                self.assertEqual(r["reason"], "policy_disabled")

    def test_daily_cap(self):
        with tempfile.TemporaryDirectory() as td:
            crumbs = Path(td) / "c.jsonl"
            day = m._utc_day()
            crumbs.write_text(
                json.dumps(
                    {
                        "utc_day": day,
                        "status": "applied",
                        "counted": True,
                        "remove": "A-USD",
                        "add": "B-USD",
                    }
                )
                + "\n"
            )
            with patch.object(m, "KILL", Path(td) / "nope"), patch.object(
                m, "DECISION", Path(td) / "dec.json"
            ), patch.object(m, "RECEIPT", Path(td) / "r.json"), patch.object(
                m, "CRUMBS", crumbs
            ), patch.object(
                m, "preflight", return_value={"ok": True, "blockers": [], "notes": [], "novelty_blocked": False}
            ):
                (Path(td) / "dec.json").write_text(
                    json.dumps(
                        {
                            "preferred_arm": "rel_btc_stable",
                            "preferred_arm_auto_membership": {
                                "enabled": True,
                                "max_per_day": 1,
                            },
                        }
                    )
                )
                r = m.try_auto_from_bundle(_bundle_pref_ok(), dry_run=False)
                self.assertEqual(r["status"], "skipped")
                self.assertTrue(str(r["reason"]).startswith("daily_cap"))

    def test_preflight_sticky(self):
        with patch.object(m, "_pairs", return_value=["BTC-USD", "SOL-USD"]), patch.object(
            m, "_holdings", return_value={"BTC-USD": 0.0}
        ):
            pf = m.preflight("BTC-USD", "AAA-USD", protect_usd=5.0)
            self.assertFalse(pf["ok"])
            self.assertTrue(any("sticky" in b for b in pf["blockers"]))

    def test_preflight_protects_tryout_shell(self):
        """$25 tryout must not auto-eject; only orphan dust (<~$5)."""
        with patch.object(m, "_pairs", return_value=["AAA-USD", "BTC-USD"]), patch.object(
            m, "_holdings", return_value={"AAA-USD": 25.0}
        ):
            pf = m.preflight("AAA-USD", "BBB-USD", protect_usd=5.0)
            self.assertFalse(pf["ok"])
            self.assertTrue(any("remove_held" in b for b in pf["blockers"]))

    def test_preflight_allows_orphan_dust(self):
        with patch.object(m, "_pairs", return_value=["AAA-USD", "BTC-USD"]), patch.object(
            m, "_holdings", return_value={"AAA-USD": 3.0}
        ):
            pf = m.preflight("AAA-USD", "BBB-USD", protect_usd=5.0)
            self.assertTrue(pf["ok"], pf)

    def test_telegram_applied(self):
        msg = m.telegram_notice(
            {
                "status": "applied",
                "remove": "OLD-USD",
                "add": "NEW-USD",
                "preferred_arm": "rel_btc_stable",
                "novelty_override_used": False,
            }
        )
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("AUTO membership", msg)
        self.assertIn("OLD-USD", msg)
        self.assertIn("no orders", msg)

    def test_telegram_skip_quiet(self):
        self.assertIsNone(
            m.telegram_notice(
                {"status": "skipped", "reason": "no_preferred_membership_ok_write"}
            )
        )

    def test_serious_strips_preferred_when_auto_handled(self):
        bundle = _bundle_pref_ok()
        bundle["dual_agree"] = {
            "this_run": {"agreed": True, "remove": "DA-USD", "add": "DB-USD"},
            "new_agreements": [],
        }
        auto = {
            "status": "applied",
            "preferred_arm": "rel_btc_stable",
            "remove": "OLD-USD",
            "add": "NEW-USD",
        }
        with patch(
            "phase6.core.basket_swap_shadow_cf.BRAD_DECISION_JSON"
        ) as p:
            p.exists.return_value = False
            msg = m.serious_consider_with_auto(bundle, auto_result=auto)
        self.assertIsNotNone(msg)
        assert msg is not None
        # auto notice + dual GO still present
        self.assertIn("AUTO membership", msg)
        self.assertIn("DA-USD", msg)
        self.assertIn("dual_agree", msg)


if __name__ == "__main__":
    unittest.main()
