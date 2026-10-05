#!/usr/bin/env python3
"""Isolation tests for analyst weekly 7d trade review fact pack."""
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

from phase6.core import analyst_weekly_trade_review as m  # noqa: E402


def _ts(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class TestAnalystWeeklyTradeReview(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "trades.jsonl"
        self.state = self.root / "state.json"
        self.report = self.root / "report.md"
        self._orig_state = m.STATE_PATH
        self._orig_report = m.REPORT_PATH
        m.STATE_PATH = self.state
        m.REPORT_PATH = self.report

    def tearDown(self) -> None:
        m.STATE_PATH = self._orig_state
        m.REPORT_PATH = self._orig_report
        self.tmp.cleanup()

    def _write_ledger(self, rows: list[dict]) -> None:
        with self.ledger.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_summarize_primary_vs_stable_and_tax(self) -> None:
        rows = [
            {
                "pair": "LINK-USD",
                "side": "BUY",
                "timestamp": _ts(20),
                "pnl": None,
            },
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "timestamp": _ts(18),
                "reason": "tryout_scale_window_eject",
                "pnl": -0.5,
            },
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "timestamp": _ts(10),
                "reason": "take_profit_trail",
                "pnl": 2.0,
            },
            {
                "pair": "USDT-USD",
                "side": "SELL",
                "timestamp": _ts(5),
                "reason": "rotation_exchange",
                "pnl": 0.01,
            },
            {
                "pair": "ETH-USD",
                "side": "SELL",
                "timestamp": _ts(4),
                "reason": "stop_loss_exchange",
                "pnl": -1.25,
            },
        ]
        # parse through reader
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        parsed = m._read_ledger(self.ledger if False else self.ledger, since, now)
        self._write_ledger(rows)
        parsed = m._read_ledger(self.ledger, since, now)
        self.assertEqual(len(parsed), 5)
        summary = m.summarize_legs(parsed)
        self.assertEqual(summary["n_primary_buys"], 1)
        self.assertEqual(summary["n_primary_sells"], 3)
        self.assertGreaterEqual(summary["n_stable_legs"], 1)
        self.assertEqual(summary["n_green_exits"], 1)
        self.assertEqual(summary["n_red_exits"], 2)
        self.assertAlmostEqual(summary["realized_pnl_usd"], 2.0 - 0.5 - 1.25, places=4)
        self.assertLess(summary["process_tax_usd"], 0)
        self.assertIn("same_day_buy_sell_pair_days", summary)

    def test_same_day_loop_detected(self) -> None:
        day_h = 6.0
        rows = [
            {"pair": "HYPE-USD", "side": "BUY", "timestamp": _ts(day_h + 2), "pnl": None},
            {
                "pair": "HYPE-USD",
                "side": "SELL",
                "timestamp": _ts(day_h),
                "reason": "tryout_scale_window_eject",
                "pnl": -0.2,
            },
        ]
        self._write_ledger(rows)
        now = datetime.now(timezone.utc)
        parsed = m._read_ledger(self.ledger, now - timedelta(days=7), now)
        summary = m.summarize_legs(parsed)
        self.assertGreaterEqual(summary["same_day_buy_sell_pair_days"], 1)

    def test_seed_hypotheses_tryout_and_tax(self) -> None:
        summary = {
            "exit_buckets": {"scale_window_eject": 5, "sl_exchange": 2},
            "exit_reasons_top": [("tryout_scale_window_eject", 5)],
            "process_tax_usd": -8.0,
            "non_tax_usd": 1.0,
            "exit_wr": 0.3,
            "n_primary_sells": 10,
            "same_day_buy_sell_pair_days": 3,
            "pairs_pnl_worst": [{"pair": "LINK-USD", "pnl_usd": -5.0, "n_sells": 3}],
        }
        seeds = m._seed_hypotheses(summary, {"util_pct": 15.0, "regime": "flat"})
        ids = {s["id"] for s in seeds}
        self.assertIn("seed_cut_process_tax", ids)
        self.assertIn("seed_tryout_intake_quality", ids)
        self.assertIn("seed_same_day_churn", ids)
        self.assertIn("seed_exit_wr", ids)
        self.assertIn("seed_underdeploy_flat", ids)

    def test_seed_eject_cohort_zero_kindling(self) -> None:
        summary = {
            "exit_buckets": {},
            "exit_reasons_top": [],
            "process_tax_usd": 0.0,
            "non_tax_usd": 0.0,
            "exit_wr": None,
            "n_primary_sells": 0,
            "same_day_buy_sell_pair_days": 0,
            "pairs_pnl_worst": [],
        }
        seeds = m._seed_hypotheses(
            summary,
            {
                "eject_cohort_card": {
                    "n_ejects": 8,
                    "pct_cleared_live_kindling": 0.0,
                }
            },
        )
        ids = {s["id"] for s in seeds}
        self.assertIn("seed_eject_cohort_zero_kindling", ids)

    def test_build_fact_pack_write(self) -> None:
        rows = [
            {
                "pair": "SOL-USD",
                "side": "BUY",
                "timestamp": _ts(30),
                "pnl": None,
            },
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "timestamp": _ts(20),
                "reason": "take_profit_trail",
                "pnl": 1.5,
            },
        ]
        self._write_ledger(rows)
        # monkeypatch live context to avoid heavy deps
        orig_ctx = m._live_context
        m._live_context = lambda: {  # type: ignore
            "regime": "flat",
            "util_pct": 18.0,
            "nav": {"equity": 2300, "util_pct": 18.0},
            "eject_cohort_card": {
                "n_ejects": 8,
                "pct_cleared_live_kindling": 0.0,
                "pnl_net_usd": -2.99,
                "rt_fee_usd": 3.28,
                "plain": "8 ejects, 0% cleared kindling.",
            },
        }
        try:
            payload = m.build_fact_pack(
                lookback_days=7,
                ledger_path=self.ledger,
                write=True,
                refresh_attribution=False,
            )
        finally:
            m._live_context = orig_ctx
        self.assertEqual(payload["schema"], m.SCHEMA)
        self.assertTrue(self.state.exists())
        self.assertTrue(self.report.exists())
        self.assertIn("seed_hypotheses", payload)
        card = m.format_tg_card(payload)
        self.assertIn("Analyst weekly 7d", card)
        self.assertIn("plain English", card)
        self.assertIn("PnL", card)
        self.assertIn("Eject cohort", card)
        brief = payload.get("agent_brief") or {}
        contract = brief.get("output_contract") or []
        self.assertTrue(any(str(x).startswith("0) PLAIN ENGLISH") for x in contract))
        self.assertTrue(any("Eject cohort card" in str(x) for x in contract))
        rules = brief.get("rules") or []
        self.assertTrue(any("Plain English" in str(x) for x in rules))
        self.assertTrue(any("eject_cohort_card" in str(x) for x in rules))
        md = self.report.read_text(encoding="utf-8")
        self.assertIn("E-EJECT-COHORT-CARD", md)

    def test_tg_card_with_suggestions(self) -> None:
        payload = {
            "summary": {
                "realized_pnl_usd": 4.6,
                "exit_wr": 0.38,
                "process_tax_usd": -2.0,
                "n_primary_buys": 10,
                "n_primary_sells": 9,
                "same_day_buy_sell_pair_days": 2,
            },
            "context": {"nav": {"util_pct": 18}, "scoreboard": {"path_health": "sideways", "goal_label": "STABILIZE"}, "regime": "flat"},
            "seed_hypotheses": [],
        }
        card = m.format_tg_card(payload, suggestions=["Tighten tryout door", "Raise kindling bar"])
        self.assertIn("Tighten tryout door", card)


if __name__ == "__main__":
    unittest.main()
