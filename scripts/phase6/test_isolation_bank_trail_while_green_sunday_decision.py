#!/usr/bin/env python3
"""Isolation tests for bank/trail Sunday decision gates (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.core import bank_trail_while_green_decision as d  # noqa: E402


def _leg(pair: str, arm_deltas: dict[str, float], would: bool = True) -> dict:
    out = {"pair": pair, "actual_pnl_usd": -10.0}
    for k in ("A", "C", "AC"):
        out[k] = {
            "would_arm": would,
            "pnl_usd": -10.0 + arm_deltas.get(k, 0.0),
            "delta_vs_actual_usd": arm_deltas.get(k, 0.0),
        }
    return out


def _cf(legs: list[dict], winner: str | None = None) -> dict:
    # rebuild would_arm_only stats like summarize would
    armed = [r for r in legs if r["A"].get("would_arm") or r["C"].get("would_arm")]

    def stats(key: str, subset: list) -> dict:
        deltas = [float(r[key]["delta_vs_actual_usd"]) for r in subset]
        s = sorted(deltas)
        med = s[len(s) // 2] if s else 0.0
        return {
            "n": len(subset),
            "sum_delta_vs_actual_usd": round(sum(deltas), 4),
            "median_delta_vs_actual_usd": round(med, 4),
            "sum_pnl_usd": 0.0,
        }

    wo = {k: stats(k, armed) for k in ("A", "C", "AC")}
    if winner is None and armed:
        winner = max(("A", "C", "AC"), key=lambda k: wo[k]["sum_delta_vs_actual_usd"])
    return {
        "as_of": "test",
        "since": "2026-08-06",
        "summary": {
            "n_legs": len(legs),
            "n_would_arm_legs": len(armed),
            "would_arm_only": wo,
            "winner_would_arm_only": winner,
            "actual_pnl_sum": -10.0 * len(legs),
        },
        "legs": legs,
    }


GATES = {
    "min_would_arm_legs": 5,
    "min_sum_delta_usd": 15.0,
    "min_median_delta_usd": 0.5,
    "max_single_leg_share_of_abs_sum_delta": 0.55,
    "require_winner_beats_second_by_usd": 5.0,
    "require_live_apply_still_false": True,
}


class TestBankTrailSundayDecision(unittest.TestCase):
    def test_n_insufficient(self):
        legs = [
            _leg("ETH-USD", {"A": 1, "C": 5, "AC": 3}),
            _leg("BTC-USD", {"A": 1, "C": 4, "AC": 2}),
            _leg("SOL-USD", {"A": 0.5, "C": 3, "AC": 1}),
        ]
        dec = d.evaluate_decision(
            _cf(legs),
            decision_cfg={"gates": GATES, "live_apply": False, "verdicts": {}, "do_not": []},
            shadow_cfg={"live_apply": False},
        )
        self.assertEqual(dec["verdict"], "N_INSUFFICIENT")
        self.assertIsNone(dec["recommend_arm"])
        self.assertFalse(dec["checks"]["n_would_arm_legs"]["pass"])

    def test_ready_for_letter_go(self):
        # 5 legs, C clearly wins with diversified deltas
        base = [
            _leg("ETH-USD", {"A": 2, "C": 6, "AC": 4}),
            _leg("BTC-USD", {"A": 1, "C": 5, "AC": 3}),
            _leg("SOL-USD", {"A": 1, "C": 5, "AC": 2}),
            _leg("LINK-USD", {"A": 0.5, "C": 4, "AC": 2}),
            _leg("ADA-USD", {"A": 1, "C": 5, "AC": 3}),
        ]
        # C sum=25, med=5, second A sum=5.5, gap=19.5, shares low
        dec = d.evaluate_decision(
            _cf(base),
            decision_cfg={"gates": GATES, "live_apply": False, "verdicts": {}, "do_not": []},
            shadow_cfg={"live_apply": False},
        )
        self.assertEqual(dec["verdict"], "READY_FOR_LETTER_GO")
        self.assertEqual(dec["recommend_arm"], "C")
        self.assertTrue(dec["checks"]["n_would_arm_legs"]["pass"])
        self.assertIn("C", dec["letter_go_line"] or "")

    def test_signal_thin_single_leg_dominance(self):
        # n=5 but one monster leg dominates C
        legs = [
            _leg("ETH-USD", {"A": 1, "C": 40, "AC": 2}),
            _leg("BTC-USD", {"A": 1, "C": 1, "AC": 1}),
            _leg("SOL-USD", {"A": 1, "C": 1, "AC": 1}),
            _leg("LINK-USD", {"A": 1, "C": 1, "AC": 1}),
            _leg("ADA-USD", {"A": 1, "C": 1, "AC": 1}),
        ]
        dec = d.evaluate_decision(
            _cf(legs),
            decision_cfg={"gates": GATES, "live_apply": False, "verdicts": {}, "do_not": []},
            shadow_cfg={"live_apply": False},
        )
        self.assertEqual(dec["verdict"], "SIGNAL_THIN")
        self.assertIsNone(dec["recommend_arm"])
        self.assertIn("single_leg_share", dec["failures"])

    def test_blocked_live_flag(self):
        legs = [_leg("ETH-USD", {"A": 1, "C": 5, "AC": 3}) for _ in range(5)]
        dec = d.evaluate_decision(
            _cf(legs),
            decision_cfg={"gates": GATES, "live_apply": False, "verdicts": {}, "do_not": []},
            shadow_cfg={"live_apply": True},
        )
        self.assertEqual(dec["verdict"], "BLOCKED_LIVE_FLAG")

    def test_tg_card_nonempty(self):
        legs = [_leg("ETH-USD", {"A": 1, "C": 2, "AC": 1.5})]
        dec = d.evaluate_decision(
            _cf(legs),
            decision_cfg={"gates": GATES, "live_apply": False, "verdicts": {}, "do_not": ["x"]},
            shadow_cfg={"live_apply": False},
        )
        card = d.format_tg_card(dec)
        self.assertIn("MEASURE_ONLY", card)
        self.assertIn("N_INSUFFICIENT", card)
        self.assertTrue(len(card) > 40)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestBankTrailSundayDecision)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("ALL PASS test_isolation_bank_trail_while_green_sunday_decision")


if __name__ == "__main__":
    main()
