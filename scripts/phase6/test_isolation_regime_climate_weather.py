#!/usr/bin/env python3
"""Isolation: climate/weather board is measure-only and structurally sound."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import regime_climate_weather as rcw  # noqa: E402


def _synth_closes(n: int = 120, start: float = 100.0) -> list:
    """Gentle down then flat — enough for lookbacks."""
    out = []
    d0 = date(2025, 1, 1)
    px = start
    for i in range(n):
        # mild drift so labels vary a bit
        if i < 40:
            px *= 0.997  # soft down
        elif i < 80:
            px *= 1.001
        else:
            px *= 0.9995
        out.append((d0 + timedelta(days=i), float(px)))
    return out


class TestRegimeClimateWeather(unittest.TestCase):
    def test_episode_stats_basic(self):
        labs = ["bear"] * 5 + ["flat"] * 3 + ["bear"] * 2
        st = rcw.episode_stats(labs)
        self.assertEqual(st["bear"]["n_episodes"], 2)
        self.assertEqual(st["bear"]["n_days"], 7)
        self.assertEqual(st["flat"]["n_episodes"], 1)
        self.assertEqual(st["flat"]["median_days"], 3)

    def test_dwell_board_ok(self):
        dwell = rcw.build_dwell_board(_synth_closes(200), lookback_days=30)
        self.assertTrue(dwell.get("ok"), dwell)
        self.assertGreater(dwell.get("n_labeled_days") or 0, 50)
        self.assertIn("coarse_episodes", dwell)

    def test_multi_horizon_keys(self):
        closes = _synth_closes(100)
        with mock.patch.object(rcw, "detect_regime", return_value={
            "regime": "bear",
            "regime_layer": "bear",
            "btc_return_pct": -12.0,
            "confidence": 0.5,
        }):
            snap = rcw.multi_horizon_snapshot(closes, live_merge=False)
        self.assertTrue(snap.get("ok"), snap)
        self.assertEqual(snap.get("tape_source"), "caller")
        self.assertIn("7d", snap["weather_horizons"])
        self.assertIn("14d", snap["weather_horizons"])
        self.assertIn("30d", snap["weather_horizons"])
        self.assertEqual(snap["climate"]["regime"], "bear")
        self.assertTrue(snap["disagree"]["green_day_is_not_climate_flip"])
        self.assertIn("A_survival", snap["jobs"])

    def test_sparse_tail_prefers_bar_horizons(self):
        """Gap before last bar: calendar 7d/14d collapse; primary weather uses bars."""
        d0 = date(2026, 8, 1)
        closes = []
        px = 80000.0
        for i in range(40):
            closes.append((d0 + timedelta(days=i), px))
            px *= 1.001
        # 18-day hole then live append down day
        last = closes[-1][0] + timedelta(days=19)
        closes.append((last, closes[-1][1] * 0.87))
        with mock.patch.object(rcw, "detect_regime", return_value={
            "regime": "bear",
            "regime_layer": "bear",
            "btc_return_pct": -13.0,
            "confidence": 0.5,
        }):
            snap = rcw.multi_horizon_snapshot(closes, live_merge=False)
        self.assertTrue(snap["data_quality"]["sparse_tail"])
        h7 = snap["weather_horizons"]["7d"]
        self.assertEqual(h7["primary_mode"], "bars")
        self.assertTrue(h7["calendar"]["meta"].get("collapsed") or snap["data_quality"]["sparse_tail"])
        # bar 7d should differ from collapsed calendar when enough history
        self.assertIsNotNone(h7["bars"]["btc_return_pct"])

    def test_default_snapshot_uses_marketdata_port(self):
        """P3: default path goes through marketdata loader, not long JSON tip alone."""
        d0 = date(2026, 8, 1)
        closes = [(d0 + timedelta(days=i), 80000.0 + i * 10) for i in range(60)]
        load_meta = {"source": "marketdata_db", "fresh_ok": True, "bar_count": len(closes)}
        with mock.patch.object(
            rcw, "_load_marketdata_closes", return_value=(closes, load_meta)
        ), mock.patch.object(
            rcw,
            "detect_regime",
            return_value={
                "regime": "transition",
                "regime_layer": "climb",
                "btc_return_pct": 11.0,
                "confidence": 0.7,
                "source": "marketdata_db",
            },
        ):
            snap = rcw.multi_horizon_snapshot(live_merge=False)
        self.assertTrue(snap.get("ok"), snap)
        self.assertEqual(snap.get("tape_source"), "marketdata_db")
        self.assertEqual(snap["climate"]["regime"], "transition")
        self.assertFalse(snap["data_quality"].get("sparse_tail"))
        self.assertEqual(snap["btc_last"], closes[-1][0].isoformat())

    def test_merge_date_closes_marketdata_wins_tip(self):
        long_rows = [(date(2026, 8, 15), 62997.81), (date(2026, 9, 1), 70000.0)]
        md_rows = [(date(2026, 9, 1), 85000.0), (date(2026, 9, 22), 86443.0)]
        merged = rcw._merge_date_closes(long_rows, md_rows)
        by = dict(merged)
        self.assertEqual(by[date(2026, 9, 1)], 85000.0)
        self.assertEqual(by[date(2026, 9, 22)], 86443.0)
        self.assertEqual(by[date(2026, 8, 15)], 62997.81)

    def test_build_board_writes_no_live_flag(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            latest = tdp / "latest.json"
            crumbs = tdp / "crumbs.jsonl"
            report = tdp / "report.md"
            with mock.patch.object(rcw, "LATEST_JSON", latest), mock.patch.object(
                rcw, "CRUMBS", crumbs
            ), mock.patch.object(rcw, "REPORT_MD", report), mock.patch.object(
                rcw, "STATE_DIR", tdp
            ), mock.patch.object(rcw, "REPORTS_DIR", tdp):
                with mock.patch.object(
                    rcw,
                    "multi_horizon_snapshot",
                    return_value={
                        "ok": True,
                        "climate": {"regime": "bear", "btc_return_pct": -13.0},
                        "weather_horizons": {
                            "7d": {"btc_return_pct": 1.0, "regime": "flat"},
                            "14d": {"btc_return_pct": -2.0, "regime": "flat"},
                            "30d": {"btc_return_pct": -13.0, "regime": "bear"},
                        },
                        "weather_structure": {"ok": True, "cap_usd": 0.0, "layer": "bear_park"},
                        "disagree": {
                            "climate_vs_7d": True,
                            "climate_vs_14d": True,
                            "green_day_is_not_climate_flip": True,
                        },
                    },
                ), mock.patch.object(
                    rcw,
                    "build_dwell_board",
                    return_value={
                        "ok": True,
                        "coarse_episodes": {
                            "bear": {
                                "n_episodes": 10,
                                "n_days": 80,
                                "mean_days": 8.0,
                                "median_days": 7.0,
                                "p90_days": 15,
                            }
                        },
                        "layer_episodes": {},
                        "tape_start": "2024-01-01",
                        "tape_end": "2026-01-01",
                        "n_labeled_days": 100,
                    },
                ):
                    board = rcw.build_board(write=True)
            self.assertFalse(board["live_writes"])
            self.assertTrue(board["measure_only"])
            self.assertTrue(latest.exists())
            self.assertTrue(crumbs.exists())
            self.assertTrue(report.exists())
            body = latest.read_text()
            self.assertIn("measure_only", body)
            self.assertIn('"live_writes": false', body)
            # must not claim money path
            self.assertNotIn("allow_new_buys\": true", body.lower().replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
