#!/usr/bin/env python3
"""Isolation: A2 tryout sent latch + B1 tryout floor (no stack with new_pair)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.tryout_sent_latch import (
    apply_latch_to_sentiment,
    write_latches_from_scores,
    load_latch,
)
from phase6.core.regime_cash_policy import evaluate_buy_entry


def _snap(**kw):
    base = dict(
        allow_new_buys=True,
        strategy_mode="deploy",
        entry={"min_sentiment": 0.25, "min_sentiment_new_pair": 0.35, "max_rsi": 70.0},
        regime="soft_down",
        equity_health="soft_down",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _tryout_pol(*, skip_latch: bool = False) -> dict:
    pol = {
        "_isolation_skip_process_tax": True,
        "entry_gates": {
            "min_sentiment": 0.25,
            "min_sentiment_new_pair": 0.35,
            "max_rsi": 70.0,
        },
        "operator_override": {
            "recovery_soft_down_20260828": {
                "enabled": True,
                "new_alt_policy": "quality_tryout",
                "allowlist_pairs": ["PAXG-USD"],
                "quality_tryout": {
                    "tryout_pairs": ["ETH-USD", "AVAX-USD"],
                    "min_sentiment": 0.30,
                    "max_rsi": 65.0,
                    "max_new_seats_per_day": 99,
                    "abs_cap_usd": 75.0,
                },
            }
        },
    }
    if skip_latch:
        pol["_isolation_skip_tryout_latch"] = True
    return pol


class TestTryoutSentLatchA2B1(unittest.TestCase):
    def test_write_and_apply_latch_through_decay(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "latch.json"
            now = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
            write_latches_from_scores(
                {"ETH-USD": 0.58, "AVAX-USD": 0.05},
                tryout_pairs=["ETH-USD", "AVAX-USD"],
                floor=0.30,
                source="x_refresh",
                ttl_min=45.0,
                now=now,
                path=path,
            )
            st = load_latch(path)
            self.assertIn("ETH-USD", st["pairs"])
            self.assertNotIn("AVAX-USD", st["pairs"])

            later = now + timedelta(minutes=17)
            sent, note = apply_latch_to_sentiment(
                "ETH-USD", 0.26, floor=0.30, now=later, path=path
            )
            self.assertAlmostEqual(sent, 0.58)
            self.assertIsNotNone(note)
            self.assertIn("tryout_sent_latch", note)

            expired = now + timedelta(minutes=50)
            sent2, note2 = apply_latch_to_sentiment(
                "ETH-USD", 0.26, floor=0.30, now=expired, path=path
            )
            self.assertAlmostEqual(sent2, 0.26)
            self.assertIsNone(note2)

    def test_evaluate_buy_b1_floor_and_latch(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "latch.json"
            now = datetime.now(timezone.utc)
            write_latches_from_scores(
                {"ETH-USD": 0.42},
                tryout_pairs=["ETH-USD"],
                floor=0.30,
                now=now,
                path=path,
            )
            import phase6.core.tryout_sent_latch as latch_mod

            old = latch_mod.STATE_PATH
            latch_mod.STATE_PATH = path
            try:
                d = evaluate_buy_entry(
                    "ETH-USD",
                    _snap(),
                    sentiment=0.26,
                    rsi=50.0,
                    is_new_pair=True,
                    policy=_tryout_pol(),
                )
                sent_fail = [r for r in d.reasons if "sentiment" in r and "< min" in r]
                self.assertEqual(sent_fail, [], msg=list(d.reasons))
                for r in d.reasons:
                    self.assertNotIn("< min 0.35", r)
            finally:
                latch_mod.STATE_PATH = old

    def test_b1_tryout_floor_not_stacked_without_latch(self):
        """eng 0.32: fail under old max(0.35,0.30); pass under B1 tryout 0.30."""
        d = evaluate_buy_entry(
            "ETH-USD",
            _snap(),
            sentiment=0.32,
            rsi=50.0,
            is_new_pair=True,
            policy=_tryout_pol(skip_latch=True),
        )
        sent_fail = [r for r in d.reasons if "sentiment" in r and "< min" in r]
        self.assertEqual(sent_fail, [], msg=list(d.reasons))
        for r in d.reasons:
            self.assertNotIn("< min 0.35", r)


if __name__ == "__main__":
    unittest.main()
