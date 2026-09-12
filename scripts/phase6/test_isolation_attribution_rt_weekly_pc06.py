#!/usr/bin/env python3
"""Isolation: PC-06 attribution RT weekly (stamps, tax, N gate)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.attribution_rt_weekly import (  # noqa: E402
    EDGE_CLAIM_MIN_N,
    build_attribution_rt_weekly,
    build_rt_rows,
    classify_exit_reason,
    coverage_flags,
    summarize_rts,
)


class TestAttributionRTWeeklyPC06(unittest.TestCase):
    def test_classify_tax(self):
        self.assertEqual(classify_exit_reason({"reason": "stop_loss_exchange"}), "sl_exchange")
        self.assertEqual(classify_exit_reason({"exit_reason": "take_profit_trail"}), "tp_profit")
        self.assertEqual(classify_exit_reason({"reason": "rotation_exchange"}), "rotation")

    def test_coverage_buy(self):
        c = coverage_flags(
            {"entry_rsi": 40.0, "entry_sentiment": 0.2, "bag_id": "X:1", "signal_stamp_schema": 1},
            side="BUY",
        )
        self.assertTrue(c["has_entry_rsi"])
        self.assertTrue(c["has_entry_sent"])
        self.assertTrue(c["has_bag_id"])

    def test_rt_match_and_tax(self):
        ledger = [
            {
                "side": "BUY",
                "pair": "ETH-USD",
                "order_id": "b1",
                "timestamp": "2026-09-08T10:00:00+00:00",
                "entry_rsi": 35.0,
                "entry_sentiment": 0.4,
                "bag_id": "ETH-USD:b1",
            },
            {
                "side": "SELL",
                "pair": "ETH-USD",
                "order_id": "s1",
                "entry_order_id": "b1",
                "timestamp": "2026-09-09T12:00:00+00:00",
                "reason": "stop_loss_exchange",
                "pnl": -3.5,
                "exit_rsi": 32.0,
                "exit_sentiment": 0.1,
            },
            {
                "side": "SELL",
                "pair": "USDT-USDC",
                "order_id": "s2",
                "timestamp": "2026-09-09T13:00:00+00:00",
                "reason": "rotation_exchange",
                "pnl": 0.01,
            },
        ]
        since = datetime(2026, 9, 1, tzinfo=timezone.utc)
        rows = build_rt_rows(ledger, since=since)
        primary = [r for r in rows if not r.get("is_stable_rotation")]
        self.assertEqual(len(primary), 1)
        self.assertTrue(primary[0]["process_tax"])
        self.assertTrue(primary[0]["full_core_stamp"])
        self.assertEqual(primary[0]["entry_rsi"], 35.0)
        s = summarize_rts(rows)
        self.assertEqual(s["n_rt_primary"], 1)
        self.assertFalse(s["edge_claim_allowed"])
        self.assertEqual(s["edge_claim_min_n"], EDGE_CLAIM_MIN_N)

    def test_no_edge_on_thin_n(self):
        rows = [
            {
                "pair": "AAA-USD",
                "process_tax": False,
                "full_core_stamp": True,
                "pnl": 1.0,
                "exit_bucket": "tp_profit",
                "is_stable_rotation": False,
            }
        ] * 5
        s = summarize_rts(rows)
        self.assertFalse(s["edge_claim_allowed"])

    def test_build_from_temp_ledger(self):
        now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            led = td_path / "trades.jsonl"
            sig = td_path / "sig.jsonl"
            rows = [
                {
                    "side": "BUY",
                    "pair": "SOL-USD",
                    "order_id": "bx",
                    "timestamp": "2026-09-10T01:00:00+00:00",
                    "entry_rsi": 40.0,
                    "entry_sentiment": 0.35,
                },
                {
                    "side": "SELL",
                    "pair": "SOL-USD",
                    "order_id": "sx",
                    "entry_order_id": "bx",
                    "timestamp": "2026-09-10T20:00:00+00:00",
                    "reason": "take_profit_trail",
                    "pnl": 4.2,
                    "exit_rsi": 55.0,
                    "exit_sentiment": 0.2,
                },
            ]
            led.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            sig.write_text("")
            p = build_attribution_rt_weekly(
                write=False,
                lookback_days=7,
                ledger_path=led,
                signal_path=sig,
                now=now,
            )
            self.assertEqual(p["summary"]["n_rt_primary"], 1)
            self.assertFalse(p["summary"]["edge_claim_allowed"])
            self.assertTrue(p["no_edge_from_thin_n"])


if __name__ == "__main__":
    unittest.main()
