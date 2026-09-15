#!/usr/bin/env python3
"""Isolation tests: RSI-event X tryout shadow pure rules (no network, no orders)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_x_tryout_shadow import (  # noqa: E402
    PairCandidate,
    ShadowConfig,
    estimate_would_pass_floor,
    evaluate_candidate_pure,
    is_eng_stale_for_event,
    is_rsi_wash,
    rank_score_for_candidate,
    select_top_k,
)


class TestRsiWash(unittest.TestCase):
    def test_wash_band(self):
        self.assertTrue(is_rsi_wash(29.8, wash_max=40.0))
        self.assertTrue(is_rsi_wash(40.0, wash_max=40.0))
        self.assertFalse(is_rsi_wash(40.1, wash_max=40.0))
        self.assertFalse(is_rsi_wash(None))
        self.assertFalse(is_rsi_wash(55.0, wash_max=40.0))


class TestEngStale(unittest.TestCase):
    def test_aged_out_dust(self):
        self.assertTrue(is_eng_stale_for_event(0.0, floor=0.30))
        self.assertTrue(is_eng_stale_for_event(-0.04, floor=0.30))
        self.assertTrue(is_eng_stale_for_event(None, floor=0.30))

    def test_already_clearing_not_stale_event(self):
        # eng already above floor → no event gap (don't spend X)
        self.assertFalse(is_eng_stale_for_event(0.45, floor=0.30, age_min=5.0))

    def test_under_floor_aged(self):
        self.assertTrue(is_eng_stale_for_event(0.10, floor=0.30, age_min=60.0))
        # fresh under floor still counts as gap needing refresh
        self.assertTrue(is_eng_stale_for_event(0.10, floor=0.30, age_min=None))


class TestWouldPass(unittest.TestCase):
    def test_fresh_x(self):
        self.assertTrue(
            estimate_would_pass_floor(0.40, floor=0.30, x_age_min=10.0, x_fresh_max_min=180.0)
        )
        self.assertFalse(
            estimate_would_pass_floor(0.06, floor=0.30, x_age_min=10.0, x_fresh_max_min=180.0)
        )

    def test_stale_unknown(self):
        self.assertIsNone(
            estimate_would_pass_floor(0.50, floor=0.30, x_age_min=999.0, x_fresh_max_min=180.0)
        )
        self.assertIsNone(
            estimate_would_pass_floor(None, floor=0.30, x_age_min=10.0, x_fresh_max_min=180.0)
        )


class TestRankAndTopK(unittest.TestCase):
    def test_deeper_wash_ranks_higher(self):
        a = rank_score_for_candidate(
            rsi=25.0, tryout_eligible=True, buy_blocked=False, would_pass_floor_est=None
        )
        b = rank_score_for_candidate(
            rsi=38.0, tryout_eligible=True, buy_blocked=False, would_pass_floor_est=None
        )
        self.assertGreater(a, b)

    def test_blocked_sinks(self):
        s = rank_score_for_candidate(
            rsi=20.0, tryout_eligible=True, buy_blocked=True, would_pass_floor_est=True
        )
        self.assertLess(s, 0)

    def test_top_k_caps_two(self):
        cfg = ShadowConfig(top_k=2, rsi_wash_max=40.0)
        pairs = [
            ("XRP-USD", 29.0),
            ("ADA-USD", 32.0),
            ("NEAR-USD", 35.0),
            ("ETH-USD", 28.0),
        ]
        cands = []
        for p, rsi in pairs:
            c = evaluate_candidate_pure(
                pair=p,
                rsi=rsi,
                eng_sent=0.0,
                eng_age_min=120.0,
                x_raw=0.05,
                x_age_min=30.0,
                tryout_eligible=True,
                buy_blocked=False,
                cfg=cfg,
            )
            cands.append(c)
        # also one not triggerable
        cands.append(
            evaluate_candidate_pure(
                pair="WLD-USD",
                rsi=60.0,
                eng_sent=0.0,
                eng_age_min=120.0,
                x_raw=None,
                x_age_min=None,
                tryout_eligible=True,
                buy_blocked=False,
                cfg=cfg,
            )
        )
        selected = select_top_k(cands, k=2)
        self.assertEqual(len(selected), 2)
        sel_pairs = {c.pair for c in selected}
        # deepest wash first: ETH 28, XRP 29
        self.assertEqual(sel_pairs, {"ETH-USD", "XRP-USD"})
        for c in cands:
            if c.pair in sel_pairs:
                self.assertTrue(c.would_query_x)
                self.assertTrue(c.selected_top_k)
            else:
                self.assertFalse(c.selected_top_k)

    def test_xrp_only_override_still_top_k(self):
        cfg = ShadowConfig(top_k=2)
        c = evaluate_candidate_pure(
            pair="XRP-USD",
            rsi=29.8,
            eng_sent=-0.04,
            eng_age_min=200.0,
            x_raw=0.064,
            x_age_min=40.0,
            tryout_eligible=True,
            buy_blocked=False,
            cfg=cfg,
        )
        selected = select_top_k([c], k=2)
        self.assertEqual(len(selected), 1)
        self.assertTrue(selected[0].would_query_x)
        # cached X below floor
        self.assertIs(selected[0].would_pass_floor_est, False)


class TestFences(unittest.TestCase):
    def test_config_defaults_no_orders(self):
        cfg = ShadowConfig()
        self.assertFalse(cfg.place_orders)
        self.assertFalse(cfg.mutate_config)
        self.assertFalse(cfg.spend_x)


if __name__ == "__main__":
    # no tempfile pollution required — pure unit
    ok = unittest.main(verbosity=2, exit=False)
    raise SystemExit(0 if ok.result.wasSuccessful() else 1)
