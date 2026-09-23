#!/usr/bin/env python3
"""Isolation: break-even one-pager banks + TG card shape."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import break_even_one_pager as be  # noqa: E402


class TestBreakEvenOnePager(unittest.TestCase):
    def test_telegram_card_has_bar_and_verdict(self) -> None:
        payload = {
            "be_usd_mo": 150.0,
            "week_start_pt": "2026-09-23",
            "rt": {
                "n_rt_primary": 0,
                "gross_pnl_usd": 0.0,
                "process_tax_n": 0,
                "process_tax_usd": 0.0,
                "non_tax_n": 0,
                "non_tax_usd": 0.0,
                "edge_claim_allowed": False,
            },
            "vs_be": {
                "verdict": "N_INSUFFICIENT_path_proof_only",
                "net_rt_minus_est_x_to_date_usd": -3.5,
                "gross_run_rate_usd_mo_ILLUSTRATIVE": None,
                "be_gap_after_est_x_usd_mo_ILLUSTRATIVE": None,
            },
            "x_cost": {
                "est_x_usd_to_date": 3.5,
                "x_usd_per_week_assumption": 25.0,
            },
            "portfolio": {"total_usd": 2000.0, "holdings_usd": 100.0},
        }
        card = be.telegram_card(payload)
        self.assertIn("$150", card)
        self.assertIn("N_INSUFFICIENT", card)
        self.assertIn("No knobs", card)

    def test_build_writes_and_measure_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            state = tdir / "state.json"
            report = tdir / "report.md"
            fake_attr = {
                "schema": "test",
                "window_start": "2026-09-23T00:00:00+00:00",
                "window_end": "2026-09-30T00:00:00+00:00",
                "lookback_days": 7,
                "summary": {
                    "n_rt_primary": 2,
                    "process_tax_bank": {"n": 1, "pnl_sum": -1.0, "pnl_mean": -1.0},
                    "non_tax_bank": {"n": 1, "pnl_sum": 2.0, "pnl_mean": 2.0},
                    "edge_claim_allowed": False,
                    "edge_claim_min_n": 20,
                    "edge_claim_note": "thin",
                    "by_bucket": {"tp_profit": 1, "sl_exchange": 1},
                    "stamp_coverage_rate": 1.0,
                },
                "rows_primary": [
                    {"process_tax": True, "pnl_usd": -1.0, "exit_ts": "2026-09-24T12:00:00+00:00"},
                    {"process_tax": False, "pnl_usd": 2.0, "exit_ts": "2026-09-25T12:00:00+00:00"},
                ],
                "coverage_audit": {},
            }
            with mock.patch.object(be, "STATE_PATH", state), mock.patch.object(
                be, "REPORT_PATH", report
            ), mock.patch.object(
                be, "build_attribution_rt_weekly", return_value=fake_attr
            ), mock.patch.object(
                be, "_portfolio_slice", return_value={"total_usd": 100.0, "holdings_usd": 25.0, "n_risk_positions": 1, "cash_usd": 75.0, "source": "t"}
            ), mock.patch.object(
                be, "_fee_slice", return_value={"source": None}
            ), mock.patch.object(
                be,
                "_x_cost_slice",
                return_value={
                    "est_x_usd_to_date": 5.0,
                    "est_x_usd_per_month": 108.0,
                    "x_usd_per_week_assumption": 25.0,
                    "days_elapsed_in_week": 7,
                    "pair_queries_today": 0,
                    "rsi_pair_queries_today": 0,
                    "rebal_pair_queries_today": 0,
                    "probe_events_in_week_window": 0,
                    "primary_schedule": "2x",
                    "x_usd_assumption_note": "test",
                },
            ), mock.patch.object(
                be, "_regime_slice", return_value={"regime": "flat", "strategy": "deploy"}
            ):
                payload = be.build_break_even_one_pager(
                    write=True,
                    week_start_pt="2026-09-23",
                    now=datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc),
                )
            self.assertTrue(payload["measure_only"])
            self.assertTrue(payload["no_knobs"])
            self.assertEqual(payload["be_usd_mo"], 150.0)
            self.assertEqual(payload["rt"]["gross_pnl_usd"], 1.0)
            self.assertTrue(state.exists())
            self.assertTrue(report.exists())
            self.assertIn("Break-even", report.read_text())


if __name__ == "__main__":
    unittest.main()
