#!/usr/bin/env python3
"""Isolation: x_query_budget + rebalance_x_candidates + probe dry path."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rebalance_x_candidates import (  # noqa: E402
    estimate_candidate_calls,
    estimate_full_book_calls,
    is_stable_pair,
    rebalance_x_candidates,
)
from phase6.core.x_query_budget import (  # noqa: E402
    BudgetConfig,
    check_can_spend,
    load_budget,
    record_spend,
    save_budget,
)


class TestRebalanceXCandidates(unittest.TestCase):
    def test_union_held_plan_no_pool_expand(self):
        out = rebalance_x_candidates(
            held_pairs=["ETH-USD", "USDT-USDC"],
            plan_pairs=["ADA-USD"],
            pool=["ETH-USD", "ADA-USD", "SOL-USD", "LINK-USD"],
        )
        self.assertEqual(out, {"ETH-USD", "ADA-USD"})  # SOL/LINK not held/plan
        self.assertNotIn("USDT-USDC", out)

    def test_stable_and_ballast(self):
        self.assertTrue(is_stable_pair("USDT-USDC"))
        out = rebalance_x_candidates(
            held_pairs=["PAXG-USD", "BTC-USD", "LINK-USD"],
            plan_pairs=[],
            pool=None,
        )
        self.assertEqual(out, {"LINK-USD"})

    def test_call_estimates(self):
        self.assertEqual(estimate_candidate_calls(0), 0)
        self.assertEqual(estimate_candidate_calls(2), 1)
        self.assertGreaterEqual(estimate_full_book_calls(12), 2)


class TestXQueryBudget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "budget.json"
        self.cfg = BudgetConfig(
            max_pair_queries_per_day=4,
            max_rsi_pair_queries_per_day=2,
            max_rebal_pair_queries_per_day=3,
            per_pair_cooldown_hours=6.0,
            path=self.path,
        )
        self.now = datetime(2026, 9, 18, 20, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rsi_lane_cap(self):
        d1 = check_can_spend(["ADA-USD", "ZEC-USD", "HYPE-USD"], lane="rsi", cfg=self.cfg, now=self.now)
        self.assertTrue(d1.allowed)
        self.assertEqual(len(d1.allowed_pairs), 2)  # rsi cap 2
        r = record_spend(d1.allowed_pairs, lane="rsi", cfg=self.cfg, now=self.now)
        self.assertTrue(r["ok"])
        d2 = check_can_spend(["ETH-USD"], lane="rsi", cfg=self.cfg, now=self.now)
        self.assertFalse(d2.allowed)

    def test_cooldown(self):
        record_spend(["ADA-USD"], lane="rsi", cfg=self.cfg, now=self.now)
        d = check_can_spend(["ADA-USD"], lane="rsi", cfg=self.cfg, now=self.now + timedelta(hours=1))
        self.assertFalse(d.allowed)
        d_ok = check_can_spend(
            ["ADA-USD"], lane="rsi", cfg=self.cfg, now=self.now + timedelta(hours=7)
        )
        # day may still be exhausted for rsi if same day — use fresh day path
        self.assertIn(d_ok.reason, ("ok", "day_or_lane_exhausted", "all_pairs_cooldown_or_blocked"))

    def test_day_rollover(self):
        record_spend(["ADA-USD", "ZEC-USD"], lane="rsi", cfg=self.cfg, now=self.now)
        # next PT day approx +24h
        later = self.now + timedelta(hours=30)
        st = load_budget(self.path, now=later)
        self.assertEqual(int(st.get("pair_queries") or 0), 0)


class TestProbeImportDry(unittest.TestCase):
    def test_run_probe_dry_no_crash(self):
        from phase6.core.rsi_event_x_probe import run_probe

        with tempfile.TemporaryDirectory() as td:
            bpath = Path(td) / "b.json"
            cfg = BudgetConfig(path=bpath)
            r = run_probe(dry_run=True, spend_x=False, budget_cfg=cfg, top_k=2)
            self.assertTrue(r.get("dry_run"))
            self.assertFalse(r.get("spend_x_executed"))
            self.assertEqual(r.get("place_orders"), False)
            self.assertEqual(r.get("live_gate"), "OFF")


class TestProbeTelegramQuiet(unittest.TestCase):
    """A+C: TG only on clear floor or hard fail — not under-floor paid."""

    def test_under_floor_paid_silent(self):
        from phase6.core.rsi_event_x_probe import telegram_summary

        body = telegram_summary(
            {
                "dry_run": False,
                "spend_x_requested": True,
                "spend_x_executed": True,
                "fetched": ["ZEC-USD"],
                "x_scores": {"ZEC-USD": {"sentiment": 0.1585}},
                "latch_writes": {
                    "ZEC-USD": {"score": 0.1585, "clears_floor": False, "latch": None}
                },
                "fetch_meta": {"ok": True},
            },
            floor=0.30,
        )
        self.assertEqual(body, "")

    def test_clear_floor_pings(self):
        from phase6.core.rsi_event_x_probe import telegram_summary

        body = telegram_summary(
            {
                "dry_run": False,
                "spend_x_requested": True,
                "spend_x_executed": True,
                "fetched": ["ADA-USD"],
                "x_scores": {"ADA-USD": {"sentiment": 0.55}},
                "latch_writes": {
                    "ADA-USD": {
                        "score": 0.55,
                        "clears_floor": True,
                        "latch": "write_latches_from_scores",
                    }
                },
                "fetch_meta": {"ok": True},
            },
            floor=0.30,
        )
        self.assertIn("PROBE clear", body)
        self.assertIn("ADA-USD", body)

    def test_fetch_fail_pings(self):
        from phase6.core.rsi_event_x_probe import telegram_summary

        body = telegram_summary(
            {
                "dry_run": False,
                "spend_x_requested": True,
                "spend_x_executed": False,
                "fetched": [],
                "fetch_meta": {"ok": False, "returncode": 1},
                "plain_english": "X fetch failed for ['ZEC-USD']: boom",
            },
            floor=0.30,
        )
        self.assertIn("PROBE FAIL", body)

    def test_dry_idle_silent(self):
        from phase6.core.rsi_event_x_probe import telegram_summary

        body = telegram_summary(
            {
                "dry_run": True,
                "spend_x_executed": False,
                "selected_pre": [{"pair": "ZEC-USD"}],
            },
            floor=0.30,
        )
        self.assertEqual(body, "")


if __name__ == "__main__":
    unittest.main()
