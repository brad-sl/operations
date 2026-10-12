#!/usr/bin/env python3
"""Isolation tests: closed-leg backfill + winsorize for SL exit weekly."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
SCRIPT = ROOT / "scripts" / "phase6" / "sl_exit_counterfactual_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("sl_exit_cf", SCRIPT)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestClosedLegBackfill(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _load()

    def test_episodize_collapses_spam(self) -> None:
        base = datetime(2026, 10, 1, tzinfo=timezone.utc)
        events = []
        for i in range(10):
            events.append(
                {
                    "ts": (base.timestamp() + i * 60),  # bad — use iso
                }
            )
        # proper iso
        events = [
            {
                "pair": "ETH-USD",
                "kind": "rsi_hard_exit",
                "ts": datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
                "regime": "flat",
                "r": 0.02,
            },
            {
                "pair": "ETH-USD",
                "kind": "rsi_hard_exit",
                "ts": datetime(2026, 10, 1, 12, 10, tzinfo=timezone.utc).isoformat(),
                "regime": "flat",
                "r": 0.021,
            },
            {
                "pair": "ETH-USD",
                "kind": "rsi_hard_exit",
                "ts": datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc).isoformat(),
                "regime": "flat",
                "r": 0.01,
            },
        ]
        eps = self.m._episodize_events(events)
        self.assertEqual(len(eps), 2)  # 10m gap < 30m; 60m gap new

    def test_backfill_counts_sell_after_episode(self) -> None:
        events = [
            {
                "pair": "LINK-USD",
                "kind": "trail",
                "ts": "2026-10-01T10:00:00+00:00",
                "regime": "flat",
                "r": 0.05,
                "mark_px": 20.0,
            }
        ]
        sells = [
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "reason": "stop_loss_exchange",
                "timestamp": "2026-10-07T16:00:00+00:00",
                "entry_price": 20.0,
                "exit_price": 18.8,
                "qty": 1.0,
                "pnl": -1.2,
            },
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "reason": "take_profit_trail",
                "timestamp": "2026-10-08T03:00:00+00:00",
                "entry_price": 100.0,
                "exit_price": 103.0,
                "qty": 1.0,
                "pnl": 3.0,
            },
        ]
        # SOL has no episode → not counted as closed-with-signal
        coll: dict = {"by_regime": {}}
        since = datetime(2026, 8, 6, tzinfo=timezone.utc)
        bf = self.m.backfill_closed_legs(
            events=events, strategy_sells=sells, since=since, coll=coll
        )
        self.assertEqual(bf["counts_by_regime"].get("flat"), 1)
        self.assertEqual(coll["by_regime"]["flat"]["closed_legs_observed"], 1)
        self.assertEqual(coll["by_regime"]["flat"]["closed_legs_by_family"]["SL"], 1)

    def test_winsorize(self) -> None:
        xs = self.m._winsorize([-200.0, 10.0, 5.0], cap=50.0)
        self.assertEqual(xs[0], -50.0)
        self.assertEqual(xs[1], 10.0)

    def test_glossary_not_3pct(self) -> None:
        # live floor reader falls back to 0.08 without config
        # just ensure render mentions floor from layers
        d = {
            "go_no_go": "NO-GO",
            "shadow_days": 66,
            "days_needed": 60,
            "regime_now": "flat",
            "layers": {"SL_floor_live_pct": 0.08, "C_global_trail_tp": "LIVE — 0 banks"},
            "promotion": {"per_regime": {}},
            "hard_exit": {},
            "n_sl_legs": 0,
            "n_sl_with_prior_shadow": 0,
            "legs": [],
            "since": "2026-08-06",
        }
        body = self.m.render_telegram(d)
        self.assertIn("~8%", body)
        self.assertNotIn("live ~3%", body)


class TestSlWidthHelpers(unittest.TestCase):
    def test_first_touch_3_then_8(self) -> None:
        path = ROOT / "scripts" / "phase6" / "run_sl_width_3v8_cf.py"
        spec = importlib.util.spec_from_file_location("sl_w", path)
        assert spec and spec.loader
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        # entry 100; bars drift down
        t0 = 1_700_000_000.0
        candles = []
        # hour 0: high 102 low 99
        candles.append([t0, 99.0, 102.0, 100.0, 100.5])
        # hour 5: low 96.5 → 3% touch
        candles.append([t0 + 5 * 3600, 96.5, 98.0, 98.0, 97.0])
        # hour 20: low 91.5 → 8% touch
        candles.append([t0 + 20 * 3600, 91.5, 93.0, 93.0, 92.0])
        entry_ts = t0
        exit_ts = t0 + 25 * 3600
        t3 = m._first_touch(candles, entry_ts=entry_ts, exit_ts=exit_ts, entry_px=100.0, stop_pct=0.03)
        t8 = m._first_touch(candles, entry_ts=entry_ts, exit_ts=exit_ts, entry_px=100.0, stop_pct=0.08)
        self.assertTrue(t3["touched"])
        self.assertTrue(t8["touched"])
        self.assertLess(t3["ts"], t8["ts"])
        self.assertAlmostEqual(t3["stop_px"], 97.0)
        self.assertAlmostEqual(t8["stop_px"], 92.0)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
