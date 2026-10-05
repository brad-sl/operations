#!/usr/bin/env python3
"""Isolation tests for E-EJECT-COHORT-CARD (measure-only)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestEjectCohortCard(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "trades" / "phase6_trades.jsonl"
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.state = self.root / "data" / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.reports = self.root / "reports"
        self.reports.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_jsonl(self, path: Path, rows: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(r, default=str) for r in rows) + "\n",
            encoding="utf-8",
        )

    def test_zero_cleared_kindling_headline(self) -> None:
        from phase6.core import tryout_eject_cohort_card as m

        ledger_rows = [
            {
                "pair": "AAA-USD",
                "side": "BUY",
                "timestamp": "2026-10-01T10:00:00Z",
                "order_id": "b1",
                "reason": "limit_first_buy",
                "price": 10.0,
                "qty": 2.5,
            },
            {
                "pair": "AAA-USD",
                "side": "SELL",
                "timestamp": "2026-10-01T20:00:00Z",
                "order_id": "s1",
                "entry_order_id": "b1",
                "reason": "tryout_scale_window_eject",
                "entry_price": 10.0,
                "price": 10.1,
                "qty": 2.5,
                "pnl": -0.2,
                "pnl_gross": 0.25,
                "rt_fee_usd": 0.45,
            },
            {
                "pair": "BBB-USD",
                "side": "BUY",
                "timestamp": "2026-10-02T08:00:00Z",
                "order_id": "b2",
                "reason": "limit_first_buy",
            },
            {
                "pair": "BBB-USD",
                "side": "SELL",
                "timestamp": "2026-10-02T18:00:00Z",
                "order_id": "s2",
                "reason": "tryout_scale_window_eject",
                "entry_price": 5.0,
                "price": 4.9,
                "qty": 5.0,
                "pnl": -0.9,
                "pnl_gross": -0.5,
                "rt_fee_usd": 0.4,
            },
        ]
        self._write_jsonl(self.ledger, ledger_rows)
        ghosts = [
            {
                "pair": "AAA-USD",
                "why": "close_tryout_lot",
                "lot": {
                    "entry_ts": "2026-10-01T10:00:00Z",
                    "paper_scaled": True,
                    "live_scaled": False,
                    "phase": 3,
                    "structure_ok": False,
                    "status": "scored",
                },
                "purged_at": "2026-10-01T20:01:00Z",
            }
        ]
        self._write_jsonl(self.state / "tryout_open_lot_ghosts.jsonl", ghosts)
        fee_payload = {
            "cohort": [
                {
                    "pair": "AAA-USD",
                    "timestamp": "2026-10-01T20:00:00Z",
                    "order_id": "s1",
                    "pnl_gross_usd": 0.25,
                    "rt_fee_usd": 0.45,
                    "pnl_net_usd": -0.2,
                    "fee_blind_green": True,
                    "fee_aware_green": False,
                    "gross_green_net_red": True,
                },
                {
                    "pair": "BBB-USD",
                    "timestamp": "2026-10-02T18:00:00Z",
                    "order_id": "s2",
                    "pnl_gross_usd": -0.5,
                    "rt_fee_usd": 0.4,
                    "pnl_net_usd": -0.9,
                    "fee_blind_green": False,
                    "fee_aware_green": False,
                    "gross_green_net_red": False,
                },
            ]
        }

        with mock.patch.object(m, "LEDGER_PATH", self.ledger), mock.patch.object(
            m, "GHOSTS_PATH", self.state / "tryout_open_lot_ghosts.jsonl"
        ), mock.patch.object(
            m, "SHADOW_CRUMBS_PATH", self.state / "missing_shadow.jsonl"
        ), mock.patch.object(
            m, "LIVE_CRUMBS_PATH", self.state / "missing_live.jsonl"
        ), mock.patch.object(
            m, "OPEN_LOTS_PATH", self.state / "missing_lots.json"
        ), mock.patch.object(m, "LATEST_JSON", self.state / "tryout_eject_cohort_weekly.json"), mock.patch.object(
            m, "LATEST_MD", self.reports / "TRYOUT_EJECT_COHORT_CARD_LATEST.md"
        ), mock.patch.object(m, "REPORT_DIR", self.reports), mock.patch.object(
            m, "STATE_DIR", self.state
        ), mock.patch.object(m, "PROJECT_ROOT", self.root):
            payload = m.build_cohort_card(
                lookback_days=30,
                ledger_path=self.ledger,
                fee_payload=fee_payload,
            )
            self.assertEqual(payload["n_ejects"], 2)
            self.assertEqual(payload["scoreboard"]["n_cleared_live_kindling"], 0)
            self.assertEqual(payload["scoreboard"]["pct_cleared_live_kindling"], 0.0)
            self.assertFalse(payload["edge_claim_allowed"])
            aaa = next(r for r in payload["rows"] if r["pair"] == "AAA-USD")
            self.assertAlmostEqual(float(aaa["hold_h"]), 10.0, places=2)
            self.assertEqual(aaa["phase"], 3)
            self.assertIs(aaa["structure_ok"], False)
            self.assertTrue(aaa["paper_scaled"])
            self.assertFalse(aaa["cleared_live_kindling"])
            self.assertIn("paper_scaled", str(aaa["kindling_block"]))
            paths = m.write_card(payload)
            self.assertTrue(Path(paths["json"]).is_file())
            snap = m.snapshot_for_analyst(payload)
            self.assertEqual(snap["pct_cleared_live_kindling"], 0.0)
            md = m.render_markdown(payload)
            self.assertIn("0.0%", md)
            self.assertIn("Plain English", md)

    def test_cleared_when_live_scale_buy_present(self) -> None:
        from phase6.core import tryout_eject_cohort_card as m

        rows = [
            {
                "pair": "CCC-USD",
                "side": "BUY",
                "timestamp": "2026-10-01T10:00:00Z",
                "order_id": "b1",
                "reason": "limit_first_buy",
            },
            {
                "pair": "CCC-USD",
                "side": "BUY",
                "timestamp": "2026-10-01T14:00:00Z",
                "order_id": "k1",
                "reason": "tryout_scale_up_mid_flight",
                "usd": 25.0,
            },
            {
                "pair": "CCC-USD",
                "side": "SELL",
                "timestamp": "2026-10-01T22:00:00Z",
                "order_id": "s1",
                "reason": "tryout_scale_window_eject",
                "pnl": 1.0,
            },
        ]
        self._write_jsonl(self.ledger, rows)
        with mock.patch.object(m, "GHOSTS_PATH", self.state / "no_ghosts.jsonl"), mock.patch.object(
            m, "SHADOW_CRUMBS_PATH", self.state / "no_shadow.jsonl"
        ), mock.patch.object(m, "OPEN_LOTS_PATH", self.state / "no_lots.json"):
            payload = m.build_cohort_card(
                lookback_days=30,
                ledger_path=self.ledger,
                fee_payload={"cohort": []},
            )
        self.assertEqual(payload["n_ejects"], 1)
        self.assertEqual(payload["scoreboard"]["n_cleared_live_kindling"], 1)
        self.assertEqual(payload["scoreboard"]["pct_cleared_live_kindling"], 1.0)
        row = payload["rows"][0]
        self.assertTrue(row["cleared_live_kindling"])
        self.assertEqual(row["kindling_block"], "cleared_live_kindling")


if __name__ == "__main__":
    unittest.main()
