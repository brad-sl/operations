#!/usr/bin/env python3
"""Isolation: PC-05 limit-first evidence (honest zero + drought)."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.limit_first_evidence import (  # noqa: E402
    aggregate_events,
    build_limit_first_evidence,
    drought_note,
    policy_snapshot,
)


class TestLimitFirstEvidencePC05(unittest.TestCase):
    def test_aggregate_honest_zero(self):
        a = aggregate_events([])
        self.assertEqual(a["limit_attempts"], 0)
        self.assertIsNone(a["fill_rate"])
        self.assertEqual(a["market_fallback_events"], 0)

    def test_aggregate_fill_rate(self):
        ev = [
            {"ts": "2026-09-09T04:00:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "attempted"},
            {"ts": "2026-09-09T04:01:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "filled", "filled_usd": 74.0},
            {"ts": "2026-09-09T16:00:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "attempted"},
            {"ts": "2026-09-09T16:01:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "unfilled"},
        ]
        a = aggregate_events(ev)
        self.assertEqual(a["limit_attempts"], 2)
        self.assertEqual(a["limit_filled"], 1)
        self.assertEqual(a["limit_unfilled"], 1)
        self.assertAlmostEqual(a["fill_rate"], 0.5)

    def test_drought_zero_attempts(self):
        d = drought_note(attempts=0, last_ts=None, tryout_can_buy=False)
        self.assertTrue(d["drought"])
        self.assertTrue(d["honest_zero_ok"])
        self.assertFalse(d["promote_talk_ok"])
        self.assertIn("zero_limit_attempts_in_window", d["reasons"])
        self.assertIn("linked_pc03_sleeve_drought_can_buy_false", d["reasons"])

    def test_drought_stale_last_attempt(self):
        now = datetime(2026, 9, 11, tzinfo=timezone.utc)
        last = (now - timedelta(days=15)).isoformat()
        d = drought_note(attempts=2, last_ts=last, now=now, tryout_can_buy=False)
        self.assertTrue(d["drought"])
        self.assertGreaterEqual(d["days_since_last_attempt"], 14)

    def test_policy_snapshot_fallback_zero(self):
        pol = policy_snapshot(
            {
                "entry_execution": {
                    "mode": "limit_first_v1",
                    "limit_first": {
                        "enabled": True,
                        "market_fallback": False,
                        "market_fallback_max_usd": 0.0,
                    },
                }
            }
        )
        self.assertEqual(pol["market_fallback_max_usd"], 0.0)
        self.assertFalse(pol["market_fallback"])

    def test_build_with_fixture_events(self):
        now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        ev = [
            {"ts": "2026-09-09T04:00:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "attempted"},
            {"ts": "2026-09-09T04:01:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "filled", "filled_usd": 74.0},
            {"ts": "2026-09-09T16:00:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "attempted"},
            {"ts": "2026-09-09T16:01:00+00:00", "pair": "LINK-USD", "usd": 75, "outcome": "filled", "filled_usd": 74.5},
        ]
        p = build_limit_first_evidence(write=False, events=ev, now=now, lookback_days=30)
        self.assertEqual(p["schema"], "limit_first_evidence_v1")
        self.assertEqual(p["aggregate"]["limit_attempts"], 2)
        self.assertEqual(p["aggregate"]["limit_filled"], 2)
        self.assertIn("market_fallback_max_usd_is_zero", p["integrity"])


if __name__ == "__main__":
    unittest.main()
