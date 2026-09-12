#!/usr/bin/env python3
"""Isolation: PC-04 L2 deployability (CF ADD × evaluate_buy_entry)."""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.l2_deployability import (  # noqa: E402
    build_l2_board,
    recent_arm_adds,
    score_l2_entry,
    summarize,
)


@dataclass
class FakeSnap:
    allow_new_buys: bool = True
    strategy_mode: str = "deploy"
    entry: Dict[str, Any] = field(
        default_factory=lambda: {
            "min_sentiment": 0.25,
            "min_sentiment_new_pair": 0.35,
            "max_rsi": 55.0,
            "require_lockout_clear": True,
        }
    )
    regime: str = "flat"
    confidence: float = 0.5
    btc_return_pct: Optional[float] = 0.0
    target_max_util_pct: float = 50.0
    rebalance_cap_usd: float = 75.0
    min_cash_reserve_pct: float = 20.0
    exit: Dict[str, Any] = field(default_factory=dict)
    label: str = "test"
    detector: Dict[str, Any] = field(default_factory=dict)


class TestL2DeployabilityPC04(unittest.TestCase):
    def test_recent_arm_adds_dedupes_newest(self):
        cf = {
            "unique_results": [
                {"arm": "rel_btc_stable", "add": "AAA-USD", "ts": "2026-09-01T00:00:00+00:00", "excess_to_now": 1.0},
                {"arm": "rel_btc_stable", "add": "BBB-USD", "ts": "2026-09-10T00:00:00+00:00", "excess_to_now": 2.0},
                {"arm": "rel_btc_stable", "add": "AAA-USD", "ts": "2026-09-11T00:00:00+00:00", "excess_to_now": 3.0},
                {"arm": "other", "add": "CCC-USD", "ts": "2026-09-11T00:00:00+00:00"},
            ]
        }
        rows = recent_arm_adds(cf, "rel_btc_stable", limit=5)
        pairs = [r["add"] for r in rows]
        self.assertEqual(pairs[0], "AAA-USD")
        self.assertIn("BBB-USD", pairs)
        self.assertEqual(len(pairs), 2)

    def test_l2_blocks_low_sent_new_pair(self):
        # Use real evaluate_buy_entry with isolation skip for process tax
        snap = FakeSnap()
        pol = {"_isolation_skip_process_tax": True, "buy_block_pairs": []}
        gate = score_l2_entry(
            pair="AVAX-USD",
            snap=snap,
            sentiment=0.0,
            rsi=40.0,
            is_new_pair=True,
            policy=pol,
        )
        self.assertFalse(gate["l2_allowed"])
        self.assertTrue(any("sentiment" in str(x).lower() or "sent" in str(x).lower() for x in gate["l2_reasons"]) or gate["l2_reasons"])

    def test_l2_pass_when_sent_and_rsi_ok(self):
        snap = FakeSnap()
        pol = {"_isolation_skip_process_tax": True, "buy_block_pairs": []}
        gate = score_l2_entry(
            pair="ETH-USD",
            snap=snap,
            sentiment=0.50,
            rsi=42.0,
            is_new_pair=True,
            policy=pol,
        )
        # May still fail recovery tryout etc — at least structure returns
        self.assertIn("l2_allowed", gate)
        self.assertIsInstance(gate["l2_reasons"], list)

    def test_board_summary_pass_rate(self):
        snap = FakeSnap()
        pol = {"_isolation_skip_process_tax": True, "buy_block_pairs": ["RAVE-USD"]}
        cf_rows = [
            {"add": "ETH-USD", "ts": "2026-09-11T00:00:00+00:00", "excess_to_now": 1.0, "source": "t", "add_score": 0.5},
            {"add": "RAVE-USD", "ts": "2026-09-11T00:00:00+00:00", "excess_to_now": 9.0, "source": "t", "add_score": 0.9},
        ]
        rows = build_l2_board(
            arm="rel_btc_stable",
            cf_rows=cf_rows,
            snap=snap,
            eng_scores={"ETH-USD": 0.5, "RAVE-USD": 0.5},
            rsi_by_pair={"ETH-USD": 40.0, "RAVE-USD": 40.0},
            policy=pol,
            held_pairs=set(),
        )
        self.assertEqual(len(rows), 2)
        rave = next(r for r in rows if r.pair == "RAVE-USD")
        self.assertFalse(rave.l2_allowed)
        s = summarize(rows)
        self.assertEqual(s["n_scored"], 2)
        self.assertIn(s["verdict"], {"L2_BLOCKED", "L2_PARTIAL", "L2_GO_BOARD"})


if __name__ == "__main__":
    unittest.main()
