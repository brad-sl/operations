#!/usr/bin/env python3
"""Isolation tests for Alt A regime ballast CF (no network)."""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(ROOT))

from phase6.research import measure_regime_ballast_cf as m  # noqa: E402


class TestRegimeBallastCF(unittest.TestCase):
    def test_climate_thresholds(self):
        self.assertEqual(m.climate_from_r30(-12.0), "bear")
        self.assertEqual(m.climate_from_r30(-6.0), "soft_down")
        self.assertEqual(m.climate_from_r30(0.0), "flat")
        self.assertEqual(m.climate_from_r30(10.0), "bull")

    def test_normalize_park_strategy(self):
        self.assertEqual(m._normalize_climate("flat", strategy_mode="usdc_park"), "bear")
        self.assertEqual(m._normalize_climate("btc_down"), "bear")
        self.assertEqual(m._normalize_climate("bull"), "bull")

    def test_risk_weight_bear_is_cash(self):
        self.assertEqual(m.risk_weight("bear"), 0.0)
        self.assertGreater(m.risk_weight("bull"), m.risk_weight("flat"))

    def test_sim_cash_flat(self):
        d0 = date(2026, 1, 1)
        panel = []
        px = 100.0
        for i in range(10):
            panel.append(
                {
                    "d": d0 + timedelta(days=i),
                    "btc": px,
                    "eth": px,
                    "btc_ret": 0.01 if i else 0.0,
                    "eth_ret": 0.01 if i else 0.0,
                    "climate": "bull",
                    "climate_proxy": "bull",
                    "r30_btc_pct": 10.0,
                }
            )
            px *= 1.01
        cash = m.sim_path(panel, mode="cash_hold", start_nav=1000.0, fee_frac=0.0)
        self.assertAlmostEqual(cash["total_return_pct"], 0.0, places=6)
        btc = m.sim_path(panel, mode="btc_hodl", start_nav=1000.0, fee_frac=0.0)
        self.assertGreater(btc["total_return_pct"], 5.0)

    def test_gated_parks_in_bear(self):
        d0 = date(2026, 1, 1)
        panel = []
        for i in range(5):
            panel.append(
                {
                    "d": d0 + timedelta(days=i),
                    "btc": 100.0 * (0.9 ** i),
                    "eth": 100.0 * (0.9 ** i),
                    "btc_ret": -0.1 if i else 0.0,
                    "eth_ret": -0.1 if i else 0.0,
                    "climate": "bear",
                    "climate_proxy": "bear",
                    "r30_btc_pct": -20.0,
                }
            )
        g = m.sim_path(panel, mode="regime_gated_ballast", start_nav=1000.0, fee_frac=0.0)
        b = m.sim_path(panel, mode="btc_hodl", start_nav=1000.0, fee_frac=0.0)
        # gated should lose less than full btc hodl in pure bear dump
        self.assertGreater(g["total_return_pct"], b["total_return_pct"])

    def test_half_sample_windows(self):
        (s1, e1), (s2, e2) = m.half_sample_windows(date(2026, 1, 1), date(2026, 4, 30))
        self.assertEqual(s1, date(2026, 1, 1))
        self.assertLess(e1, s2)
        self.assertEqual(e2, date(2026, 4, 30))

    def test_panel_prefers_logged_stamp(self):
        btc = [(date(2026, 1, 1) + timedelta(days=i), 100.0 + i) for i in range(35)]
        eth = list(btc)
        dense = {
            "2026-02-01": {"climate": "bear", "source": "test"},
        }
        panel = m.build_aligned_panel(btc, eth, dense_day_map=dense, logged_max_age_days=3)
        row = next(r for r in panel if r["d"] == date(2026, 2, 1))
        self.assertEqual(row["climate_logged"], "bear")
        self.assertEqual(row["climate"], "bear")
        row2 = next(r for r in panel if r["d"] == date(2026, 2, 3))
        self.assertEqual(row2["climate_logged"], "bear")

    def test_fold_consistency_structure(self):
        h1 = {
            "arms": {
                "regime_gated_ballast": {"total_return_pct": 1.0},
                "regime_gated_ballast_proxy": {"total_return_pct": 0.5},
                "btc_hodl": {"total_return_pct": -2.0},
                "actual_book": {"total_return_pct": -3.0},
                "cash_hold": {"total_return_pct": 0.0},
            },
            "edge": {"edge_class": "ATTENTION_ONLY"},
        }
        h2 = {
            "arms": {
                "regime_gated_ballast": {"total_return_pct": -5.0},
                "regime_gated_ballast_proxy": {"total_return_pct": -4.0},
                "btc_hodl": {"total_return_pct": -1.0},
                "actual_book": {"total_return_pct": -8.0},
                "cash_hold": {"total_return_pct": 0.0},
            },
            "edge": {"edge_class": "unstable_or_no_edge"},
        }
        c = m.fold_consistency(h1, h2)
        self.assertIn(
            c["verdict"],
            ("MIXED_fold_dependent", "UNSTABLE_or_no_edge", "STABLE_less_loss_vs_hodl"),
        )
        self.assertIn("checks", c)


if __name__ == "__main__":
    unittest.main()
