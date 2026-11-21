#!/usr/bin/env python3
"""Isolation tests for Alt C exit-first CF (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.research import measure_exit_first_cf as m  # noqa: E402


def _bars(t0: float, path: list[tuple[float, float, float]]) -> list[list[float]]:
    out = []
    for i, (lo, hi, close) in enumerate(path):
        t = t0 + i * 3600
        mid = (lo + hi) / 2
        out.append([t, lo, hi, mid, close])
    return out


class TestExitFirstCF(unittest.TestCase):
    def test_gate_skips_mae_before_mfe(self):
        g = m.exit_first_gate(mfe=0.01, mae=-0.05)
        self.assertTrue(g["skip"])

    def test_gate_allows_when_armed(self):
        g = m.exit_first_gate(mfe=0.05, mae=-0.02)
        self.assertFalse(g["skip"])
        self.assertTrue(g["allow"])

    def test_fixed_tp_fires(self):
        t0 = 1_700_000_000.0
        window = _bars(t0, [(99, 101, 100), (100, 107, 106), (105, 106, 105.5)])
        r = m.sim_fixed_tp(
            window,
            entry_px=100.0,
            qty=1.0,
            tp_pct=0.06,
            actual_pnl=-5.0,
            exit_px=95.0,
            fee_frac=0.0,
        )
        self.assertTrue(r["fired"])
        self.assertAlmostEqual(r["pnl_usd"], 6.0, places=4)
        self.assertAlmostEqual(r["delta_vs_actual"], 11.0, places=4)

    def test_trail_locks(self):
        t0 = 1_700_000_000.0
        # arm at +4%, peak +8%, pullback 2% trail from 108 → 105.84
        window = _bars(
            t0,
            [
                (99.5, 101.0, 100.5),
                (103.0, 105.0, 104.5),  # arm
                (106.0, 108.0, 107.0),  # peak
                (105.0, 106.5, 105.5),  # trail touch ~105.84
            ],
        )
        r = m.sim_trail(
            window,
            entry_px=100.0,
            qty=1.0,
            arm_mfe=0.04,
            trail_pct=0.02,
            actual_pnl=-8.0,
            exit_px=92.0,
            fee_frac=0.0,
        )
        self.assertTrue(r["fired"])
        self.assertGreater(r["pnl_usd"], 0.0)

    def test_winsor(self):
        self.assertEqual(m._winsor(100.0), 50.0)
        self.assertEqual(m._winsor(-80.0), -50.0)


if __name__ == "__main__":
    unittest.main()
