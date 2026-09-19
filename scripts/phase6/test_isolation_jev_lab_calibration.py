#!/usr/bin/env python3
"""Isolation: Jev L4 calibration rollup (no live HTTP)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.jev_lab_calibration import (
    CalibrationConfig,
    forward_return,
    load_crumbs,
    run_calibration,
)


class TestJevLabCalibration(unittest.TestCase):
    def test_forward_return_basic(self):
        # hourly closes: t0=100, +1h, +4h
        base = 1_700_000_000.0
        candles = [
            (base, 100.0),
            (base + 3600, 101.0),
            (base + 4 * 3600, 110.0),
            (base + 24 * 3600, 120.0),
        ]
        r1 = forward_return(candles, base, 1)
        self.assertIsNotNone(r1)
        assert r1 is not None
        self.assertAlmostEqual(r1, 0.01, places=5)
        r4 = forward_return(candles, base, 4)
        assert r4 is not None
        self.assertAlmostEqual(r4, 0.10, places=5)

    def test_empty_crumbs_honest_n(self):
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            crumbs = tdir / "crumbs.jsonl"
            crumbs.write_text("", encoding="utf-8")
            latest = tdir / "cal.json"
            md = tdir / "cal.md"
            ohlcv = tdir / "ohlcv"
            ohlcv.mkdir()
            summary = run_calibration(
                CalibrationConfig(
                    crumbs_path=crumbs,
                    ohlcv_dir=ohlcv,
                    latest_path=latest,
                    md_path=md,
                    min_n_claim=20,
                    write=True,
                    refresh_ohlcv=False,
                )
            )
            self.assertEqual(summary["claim_class"], "N_INSUFFICIENT_no_edge_claim")
            self.assertEqual(summary["n_ok"], 0)
            self.assertTrue(summary["measure_only"])
            self.assertTrue(summary["would_order_always_false"])
            self.assertTrue(summary["platform_proof"]["honest_n_gate"])
            self.assertTrue(latest.is_file())

    def test_fixture_crumbs_join_and_buckets(self):
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            crumbs = tdir / "crumbs.jsonl"
            ohlcv = tdir / "ohlcv"
            ohlcv.mkdir()
            # build BTC candles around now-2h so 1h fwd exists
            now = datetime.now(timezone.utc)
            t0 = (now - timedelta(hours=6)).timestamp()
            candles = []
            px = 100.0
            for i in range(12):
                candles.append([int(t0 + i * 3600), px - 1, px + 1, px, px + (0.5 if i else 0), 1.0])
                px += 0.5
            (ohlcv / "BTC_USD_1h.json").write_text(
                json.dumps({"product": "BTC-USD", "granularity": 3600, "candles": candles}),
                encoding="utf-8",
            )
            # two crumbs: act/buy high conf vs hold
            ts_mid = datetime.fromtimestamp(t0 + 2 * 3600, tz=timezone.utc).isoformat()
            rows = [
                {
                    "ts": ts_mid,
                    "pair": "BTC-USD",
                    "ok": True,
                    "model": "typesafe/jev-test",
                    "latency_ms": 400,
                    "usage": {},
                    "answers": {
                        "action": {"type": "choice", "choice": "buy", "confidence": 0.9},
                        "regime": {"type": "choice", "choice": "trend_up", "confidence": 0.7},
                        "setup_quality": {"type": "score", "score": 2.0, "confidence": 0.6},
                        "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.2},
                        "should_trade_name_now": {"type": "noul", "noul": 0.8},
                    },
                    "paper": {
                        "paper_would_buy_tag": True,
                        "would_order": False,
                        "confidence_route": "act",
                        "reasons": ["paper_would_buy_tag"],
                    },
                    "would_order": False,
                },
                {
                    "ts": ts_mid,
                    "pair": "BTC-USD",
                    "ok": True,
                    "model": "typesafe/jev-test",
                    "latency_ms": 500,
                    "usage": {},
                    "answers": {
                        "action": {"type": "choice", "choice": "hold", "confidence": 0.4},
                        "regime": {"type": "choice", "choice": "range", "confidence": 0.5},
                        "setup_quality": {"type": "score", "score": 1.0, "confidence": 0.5},
                        "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.7},
                        "should_trade_name_now": {"type": "noul", "noul": 0.2},
                    },
                    "paper": {
                        "paper_would_buy_tag": False,
                        "would_order": False,
                        "confidence_route": "human_or_skip",
                        "reasons": ["confidence_route_human_or_skip"],
                    },
                    "would_order": False,
                },
            ]
            crumbs.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            latest = tdir / "cal.json"
            summary = run_calibration(
                CalibrationConfig(
                    crumbs_path=crumbs,
                    ohlcv_dir=ohlcv,
                    latest_path=latest,
                    md_path=tdir / "cal.md",
                    min_n_claim=20,
                    write=True,
                    refresh_ohlcv=False,
                )
            )
            self.assertEqual(summary["n_ok"], 2)
            self.assertEqual(summary["claim_class"], "N_INSUFFICIENT_no_edge_claim")
            self.assertIn("act", summary["by_confidence_route"])
            self.assertIn("human_or_skip", summary["by_confidence_route"])
            self.assertGreaterEqual(summary["n_fwd_ready"], 1)
            self.assertFalse(summary["by_confidence_route"]["act"].get("n_paper_buy") == 0)

    def test_load_crumbs_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.jsonl"
            p.write_text("not-json\n{\"ok\": true, \"ts\": \"2026-01-01T00:00:00+00:00\"}\n", encoding="utf-8")
            rows = load_crumbs(p)
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
