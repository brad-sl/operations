#!/usr/bin/env python3
"""Isolation tests: Membership Manager Phase 1 (no live exchange)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import membership_manager as mm  # noqa: E402
from phase6.core import preferred_arm_auto_membership as pam  # noqa: E402


def _bundle_pref_ok(remove="SOL-USD", add="AVAX-USD"):
    return {
        "arms_prop": {
            "written": [
                {
                    "arm": "rel_btc_stable",
                    "remove": remove,
                    "add": add,
                    "membership_potential_ok": True,
                    "add_score": 0.62,
                    "remove_score": 0.28,
                    "reason": "test preferred ok",
                }
            ]
        }
    }


class MembershipManagerIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.state = self.td / "state"
        self.state.mkdir()
        self.cfg_path = self.td / "membership_manager.json"
        self.cfg_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "live_apply": True,
                    "max_per_day": 1,
                    "protect_usd": 5.0,
                    "override_novelty": True,
                    "override_missfire": False,
                    "sources": {"preferred_arm_cf": True, "contender_vs_weak": False},
                    "sticky": ["BTC-USD", "ETH-USD"],
                    "also_honor_preferred_arm_kill": True,
                }
            )
        )
        # redirect paths
        self.patches = [
            mock.patch.object(mm, "STATE", self.state),
            mock.patch.object(mm, "CFG_PATH", self.cfg_path),
            mock.patch.object(mm, "KILL", self.state / "membership_manager_KILL"),
            mock.patch.object(mm, "RECEIPT", self.state / "membership_manager_latest.json"),
            mock.patch.object(mm, "CRUMBS", self.state / "membership_manager_crumbs.jsonl"),
            mock.patch.object(mm, "CAREER", self.state / "membership_career_ledger.json"),
            mock.patch.object(mm, "CONTENDERS", self.state / "pair_discovery_contenders.json"),
            mock.patch.object(mm, "POOL_LATEST", self.state / "pool_cycling_latest.json"),
            mock.patch.object(mm, "CF_LATEST", self.state / "basket_swap_shadow_counterfactual_latest.json"),
            mock.patch.object(mm, "IDLE_LATEST", self.state / "basket_seat_idle_latest.json"),
            mock.patch.object(mm, "DECISION", self.state / "basket_swap_brad_decision.json"),
            mock.patch.object(pam, "KILL", self.state / "preferred_arm_auto_membership_KILL"),
            mock.patch.object(pam, "CRUMBS", self.state / "preferred_arm_auto_membership_crumbs.jsonl"),
            mock.patch.object(pam, "RECEIPT", self.state / "preferred_arm_auto_membership_latest.json"),
        ]
        for p in self.patches:
            p.start()
        self.state.joinpath("basket_swap_brad_decision.json").write_text(
            json.dumps({"preferred_arm": "rel_btc_stable"})
        )

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_kill_blocks(self) -> None:
        mm.KILL.write_text("stop\n")
        r = mm.run_membership_manager(dry_run=True, bundle=_bundle_pref_ok())
        self.assertEqual(r["status"], "skipped")
        self.assertIn("kill", r["reason"])

    def test_dry_would_apply_preferred(self) -> None:
        basket = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]
        with mock.patch.object(mm, "load_trading_basket", return_value=basket), \
             mock.patch.object(pam, "preflight", return_value={
                 "ok": True,
                 "blockers": [],
                 "novelty_blocked": False,
                 "missfire_blocked": False,
                 "held_usd": 0.0,
             }):
            r = mm.run_membership_manager(dry_run=True, bundle=_bundle_pref_ok())
        self.assertEqual(r["status"], "dry_would_apply")
        self.assertEqual(r["remove"], "SOL-USD")
        self.assertEqual(r["add"], "AVAX-USD")
        self.assertEqual(r["source"], "preferred_arm_cf")
        self.assertFalse(r.get("orders"))
        self.assertFalse(r.get("brad_in_path"))

    def test_daily_cap(self) -> None:
        mm.CRUMBS.write_text(
            json.dumps(
                {
                    "utc_day": mm._utc_day(),
                    "status": "applied",
                    "counted": True,
                    "remove": "AAA-USD",
                    "add": "BBB-USD",
                }
            )
            + "\n"
        )
        basket = ["BTC-USD", "ETH-USD", "SOL-USD"]
        with mock.patch.object(mm, "load_trading_basket", return_value=basket), \
             mock.patch.object(pam, "preflight", return_value={
                 "ok": True, "blockers": [], "novelty_blocked": False
             }):
            r = mm.run_membership_manager(dry_run=False, bundle=_bundle_pref_ok())
        self.assertEqual(r["status"], "skipped")
        self.assertIn("daily_cap", r["reason"])

    def test_held_above_protect_refuses(self) -> None:
        basket = ["BTC-USD", "ETH-USD", "SOL-USD"]
        with mock.patch.object(mm, "load_trading_basket", return_value=basket), \
             mock.patch.object(pam, "preflight", return_value={
                 "ok": False,
                 "blockers": ["remove_held_77.00>=protect_5.0"],
                 "novelty_blocked": False,
                 "held_usd": 77.0,
             }):
            r = mm.run_membership_manager(dry_run=False, bundle=_bundle_pref_ok())
        self.assertEqual(r["status"], "refused")
        self.assertIn("remove_held", r["reason"])

    def test_apply_calls_promote_once(self) -> None:
        basket = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]

        def _basket():
            return list(basket)

        def _fake_promote(rem, add, **kwargs):
            if rem in basket:
                basket.remove(rem)
            if add not in basket:
                basket.append(add)
            return 0, "ok promote"

        with mock.patch.object(mm, "load_trading_basket", side_effect=_basket), \
             mock.patch.object(pam, "preflight", return_value={
                 "ok": True, "blockers": [], "novelty_blocked": False, "held_usd": 0.0
             }), \
             mock.patch.object(pam, "_run_promote", side_effect=_fake_promote) as promo:
            r = mm.run_membership_manager(dry_run=False, bundle=_bundle_pref_ok())
        self.assertEqual(r["status"], "applied")
        self.assertEqual(promo.call_count, 1)
        career = mm.load_career()
        self.assertEqual((career.get("pairs") or {}).get("AVAX-USD", {}).get("career"), "active")
        self.assertEqual((career.get("pairs") or {}).get("SOL-USD", {}).get("career"), "alumni")

    def test_contender_vs_weak_selects(self) -> None:
        cfg = mm.load_config()
        cfg["sources"] = {"preferred_arm_cf": False, "contender_vs_weak": True}
        cfg["contender"] = {
            "min_quality": 0.50,
            "min_delta_vs_weak": 0.05,
            "require_promote_eligible": True,
            "skip_pump_names": True,
        }
        self.state.joinpath("pair_discovery_contenders.json").write_text(
            json.dumps(
                {
                    "contenders": [
                        {
                            "product_id": "AVAX-USD",
                            "quality_score": 0.72,
                            "promote_eligible": True,
                            "volume_quote_usd": 5_000_000,
                            "mom_3d": 0.03,
                            "mom_7d": 0.05,
                            "ret_24h": 0.02,
                        }
                    ]
                }
            )
        )
        self.state.joinpath("pool_cycling_latest.json").write_text(
            json.dumps({"scores": {"SOL-USD": 0.20, "AVAX-USD": 0.70, "XRP-USD": 0.40}})
        )
        with mock.patch.object(mm, "load_trading_basket", return_value=["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]), \
             mock.patch.object(mm, "_holdings", return_value={"SOL-USD": 0.0, "XRP-USD": 0.0}), \
             mock.patch(
                 "phase6.core.membership_potential_gate.evaluate_membership_swap",
                 return_value=mock.Mock(
                     ok=True,
                     to_dict=lambda: {"ok": True, "reasons": [], "layer_failed": None},
                 ),
             ):
            cand = mm.contender_vs_weak_candidate(cfg)
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand["add"], "AVAX-USD")
        self.assertEqual(cand["remove"], "SOL-USD")
        self.assertTrue(cand.get("membership_potential_ok"))

    def test_dashboard_payload_shape(self) -> None:
        with mock.patch.object(mm, "load_trading_basket", return_value=["BTC-USD", "ETH-USD"]):
            p = mm.dashboard_payload()
        self.assertEqual(p["schema"], "membership_manager_dashboard_v1")
        self.assertFalse(p["brad_in_path"])
        self.assertFalse(p["dual_agree_auto"])
        self.assertIn("career_counts", p)

    def test_closed_episode_not_open(self) -> None:
        from phase6.core.promote_graduation_chart import build_episodes

        eps = build_episodes(
            [
                {
                    "pick_id": "p1",
                    "add_pair": "ICP-USD",
                    "status": "open",  # stale ledger status
                    "promoted_at": "2026-09-01T00:00:00+00:00",
                    "graduation": {
                        "stage": "filled_loss",
                        "filled": True,
                        "signaled": True,
                        "hours_to_first_fill": 405.0,
                        "realized_pnl_sum": -3.2,
                    },
                }
            ]
        )
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["status"], "closed")
        self.assertFalse(eps[0]["episode_open"])
        self.assertFalse(eps[0]["hours_to_first_fill_is_queue_age"])


if __name__ == "__main__":
    unittest.main()
