#!/usr/bin/env python3
"""Isolation tests for bank/trail-while-green triple CF (no network)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.core import bank_trail_while_green_cf as m  # noqa: E402


def _bars(entry: float, path: list[tuple[float, float, float]]) -> list[list[float]]:
    """path: list of (t, low, high) — open/close = mid."""
    out = []
    for t, lo, hi in path:
        mid = (lo + hi) / 2
        out.append([t, lo, hi, mid, mid])
    return out


class TestBankTrailWhileGreen(unittest.TestCase):
    def test_arm_bar_hits_3pct(self):
        entry = 100.0
        t0 = 1_700_000_000.0
        window = _bars(
            entry,
            [
                (t0, 99.0, 101.0),
                (t0 + 3600, 100.0, 103.5),  # +3.5% high
            ],
        )
        arm = m._arm_bar(window, entry, 0.03)
        self.assertIsNotNone(arm)
        assert arm is not None
        self.assertAlmostEqual(arm["arm_px"], 103.0, places=4)

    def test_A_partial_banks_then_residual_sl(self):
        entry = 100.0
        qty = 10.0  # $1000
        t0 = 1_700_000_000.0
        # arm at +3%, then dump to -8%
        window = _bars(
            entry,
            [
                (t0, 99.5, 101.0),
                (t0 + 3600, 102.0, 104.0),  # arm
                (t0 + 7200, 91.5, 95.0),  # through 8% stop 92
            ],
        )
        r = m.sim_A(
            window,
            entry_px=entry,
            qty=qty,
            actual_exit_px=92.0,
            actual_exit_ts=t0 + 7200,
            arm_mfe=0.03,
            partial_frac=0.33,
            residual_sl_pct=0.08,
            fee_frac=0.0,  # clean arithmetic
        )
        self.assertTrue(r["would_arm"])
        # partial 3.3 @ 103 → +9.9; residual 6.7 @ 92 → -53.6; total -43.7
        self.assertAlmostEqual(r["partial_usd"], 3.3 * 3.0, places=2)
        self.assertLess(r["pnl_usd"], 0)
        # better than full size at 92: full = 10*(92-100)= -80
        self.assertGreater(r["pnl_usd"], -80.0)

    def test_C_trail_locks_after_green(self):
        entry = 100.0
        qty = 10.0
        t0 = 1_700_000_000.0
        # +3% arm, peak +5%, then pullback to lock zone
        # lock_frac 0.35 → stop = 100 + 0.35*(peak-100); peak 105 → stop 101.75
        window = _bars(
            entry,
            [
                (t0, 99.0, 101.0),
                (t0 + 3600, 102.0, 103.5),
                (t0 + 7200, 103.0, 105.0),
                (t0 + 10800, 101.0, 102.0),  # low 101 < 101.75 if peak 105
            ],
        )
        r = m.sim_C(
            window,
            entry_px=entry,
            qty=qty,
            actual_exit_px=92.0,
            actual_exit_ts=t0 + 20000,
            arm_mfe=0.03,
            lock_frac=0.35,
            be_buffer=0.005,
            fee_frac=0.0,
        )
        self.assertTrue(r["would_arm"])
        self.assertGreater(r["pnl_usd"], 0)  # exit above entry
        self.assertGreater(r["pnl_usd"], 10 * (92 - 100))  # beat ride to -8%

    def test_AC_not_exclusive_with_A_and_C(self):
        entry = 100.0
        qty = 10.0
        t0 = 1_700_000_000.0
        window = _bars(
            entry,
            [
                (t0, 99.0, 101.0),
                (t0 + 3600, 102.0, 104.0),
                (t0 + 7200, 103.0, 106.0),
                (t0 + 10800, 101.5, 103.0),
            ],
        )
        a = m.sim_A(
            window,
            entry_px=entry,
            qty=qty,
            actual_exit_px=92.0,
            actual_exit_ts=t0 + 20000,
            arm_mfe=0.03,
            partial_frac=0.33,
            residual_sl_pct=0.08,
            fee_frac=0.0,
        )
        c = m.sim_C(
            window,
            entry_px=entry,
            qty=qty,
            actual_exit_px=92.0,
            actual_exit_ts=t0 + 20000,
            arm_mfe=0.03,
            lock_frac=0.35,
            be_buffer=0.005,
            fee_frac=0.0,
        )
        ac = m.sim_AC(
            window,
            entry_px=entry,
            qty=qty,
            actual_exit_px=92.0,
            actual_exit_ts=t0 + 20000,
            arm_mfe=0.03,
            partial_frac=0.33,
            lock_frac=0.35,
            be_buffer=0.005,
            fee_frac=0.0,
        )
        self.assertTrue(a["would_arm"] and c["would_arm"] and ac["would_arm"])
        # combo is its own number — not forced equal to A or C
        self.assertIsInstance(ac["pnl_usd"], float)

    def test_scope_excludes_shell_and_paxg(self):
        cfg = {
            "scope": {
                "min_notional_usd": 75.0,
                "core_pairs": ["BTC-USD", "ETH-USD"],
                "exclude_pairs": ["PAXG-USD"],
                "include_core_even_if_below_min_notional": True,
            }
        }
        self.assertFalse(m._in_scope("LINK-USD", 25.0, cfg))
        self.assertTrue(m._in_scope("ETH-USD", 50.0, cfg))  # core
        self.assertTrue(m._in_scope("SOL-USD", 80.0, cfg))
        self.assertFalse(m._in_scope("PAXG-USD", 200.0, cfg))

    def test_summarize_winner(self):
        rows = [
            {
                "actual_pnl_usd": -10,
                "A": {"pnl_usd": -5, "delta_vs_actual_usd": 5, "would_arm": True},
                "C": {"pnl_usd": -2, "delta_vs_actual_usd": 8, "would_arm": True},
                "AC": {"pnl_usd": -3, "delta_vs_actual_usd": 7, "would_arm": True},
            }
        ]
        s = m.summarize(rows)
        self.assertEqual(s["winner_by_sum_delta"], "C")
        self.assertEqual(s["C"]["sum_delta_vs_actual_usd"], 8.0)

    def test_reconcile_sl_fantasy_pnl(self):
        leg = {
            "entry_price": 10.0,
            "qty": 10.0,
            "exit_price": 9.2,  # -8% path → -8
            "actual_pnl_usd": 114.0,  # fantasy
        }
        m._reconcile_sl_pnl(leg)
        self.assertAlmostEqual(leg["actual_pnl_usd"], -8.0, places=4)
        self.assertEqual(leg["actual_pnl_usd_ledger"], 114.0)
        self.assertTrue(leg["pnl_reconcile_warn"]["sl_fantasy"])


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestBankTrailWhileGreen)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("ALL PASS test_isolation_bank_trail_while_green_cf")


if __name__ == "__main__":
    main()
