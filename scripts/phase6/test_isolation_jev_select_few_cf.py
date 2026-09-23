#!/usr/bin/env python3
"""Isolation: Jev select-few CF universe + paper seat + no would_order."""
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

from phase6.core import jev_select_few_cf as m  # noqa: E402


class TestJevSelectFewCf(unittest.TestCase):
    def test_resolve_universe_override(self) -> None:
        cfg = m.SelectFewConfig(pairs_override=["link-usd", "ETH-USD"], max_pairs=2)
        pairs, meta = m.resolve_select_universe(cfg)
        self.assertEqual(pairs, ["LINK-USD", "ETH-USD"])
        self.assertEqual(meta.get("source"), "pairs_override")

    def test_open_seat_requires_paper_tag(self) -> None:
        book = m._empty_book()
        row = {
            "pair": "LINK-USD",
            "model": "mock",
            "paper": {"paper_would_buy_tag": False, "would_order": False},
            "answers": {},
            "state_compact": {},
        }
        self.assertIsNone(
            m._open_paper_seat(
                book,
                pair="LINK-USD",
                entry_ts="2026-09-23T12:00:00+00:00",
                notional=25.0,
                judgment_row=row,
                max_open=4,
            )
        )
        row["paper"]["paper_would_buy_tag"] = True
        seat = m._open_paper_seat(
            book,
            pair="LINK-USD",
            entry_ts="2026-09-23T12:00:00+00:00",
            notional=25.0,
            judgment_row=row,
            max_open=4,
        )
        self.assertIsNotNone(seat)
        assert seat is not None
        self.assertEqual(seat["would_order"], False)
        self.assertEqual(len(book["open"]), 1)
        # no double open
        self.assertIsNone(
            m._open_paper_seat(
                book,
                pair="LINK-USD",
                entry_ts="2026-09-23T13:00:00+00:00",
                notional=25.0,
                judgment_row=row,
                max_open=4,
            )
        )

    def test_run_dry_measure_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            state = tdir / "latest.json"
            book_p = tdir / "book.json"
            crumbs = tdir / "crumbs.jsonl"
            budget = tdir / "budget.json"
            report = tdir / "report.md"
            with mock.patch.object(m, "STATE_PATH", state), mock.patch.object(
                m, "BOOK_PATH", book_p
            ), mock.patch.object(m, "CRUMBS_PATH", crumbs), mock.patch.object(
                m, "BUDGET_PATH", budget
            ), mock.patch.object(m, "REPORT_PATH", report), mock.patch.object(
                m, "resolve_select_universe", return_value=(["LINK-USD"], {"source": "test", "parity_ok": True, "held_included": []})
            ), mock.patch.object(m, "refresh_ohlcv_1h", return_value={"skipped": []}):
                cfg = m.SelectFewConfig(
                    dry_run=True,
                    refresh_ohlcv=False,
                    write=True,
                    pairs_override=["LINK-USD"],
                    max_calls_per_day=5,
                )
                # force budget paths inside lab via run_lab LabConfig — already patched BUDGET
                payload = m.run_select_few_cf(
                    cfg=cfg, now=datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
                )
            self.assertTrue(payload["measure_only"])
            self.assertTrue(payload["would_order_always_false"])
            self.assertTrue(state.exists())
            self.assertIn("Jev select-few", report.read_text())
            card = m.telegram_card(payload)
            self.assertIn("measure-only", card)
            self.assertIn("No orders", card)

    def test_weekly_rollup_empty_book(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            book_p = tdir / "book.json"
            book_p.write_text(json.dumps(m._empty_book()), encoding="utf-8")
            wstate = tdir / "weekly.json"
            wrep = tdir / "weekly.md"
            crumbs = tdir / "crumbs.jsonl"
            with mock.patch.object(m, "BOOK_PATH", book_p), mock.patch.object(
                m, "WEEKLY_STATE_PATH", wstate
            ), mock.patch.object(m, "WEEKLY_REPORT_PATH", wrep), mock.patch.object(
                m, "CRUMBS_PATH", crumbs
            ), mock.patch.object(m, "BUDGET_PATH", tdir / "budget.json"):
                payload = m.build_weekly_rollup(
                    lookback_days=7,
                    now=datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc),
                    write=True,
                    book_path=book_p,
                )
            self.assertTrue(payload["measure_only"])
            self.assertEqual(payload["week"]["n_closed"], 0)
            self.assertIn("N_INSUFFICIENT", payload["claim_class"])
            card = m.weekly_telegram_card(payload)
            self.assertIn("weekly", card.lower())
            self.assertIn("Paper only", card)
            self.assertTrue(wstate.exists())
            self.assertIn("weekly rollup", wrep.read_text().lower())

    def test_weekly_rollup_counts_closed_in_window(self) -> None:
        book = m._empty_book()
        book["closed"] = [
            {
                "pair": "ETH-USD",
                "entry_ts": "2026-09-24T12:00:00+00:00",
                "exit_ts": "2026-09-25T12:00:00+00:00",
                "realized_pnl_usd": 1.25,
                "status": "closed_cf",
            },
            {
                "pair": "LINK-USD",
                "entry_ts": "2026-09-10T12:00:00+00:00",
                "exit_ts": "2026-09-11T12:00:00+00:00",
                "realized_pnl_usd": -0.5,
                "status": "closed_cf",
            },
        ]
        book["banks"] = {
            "realized_pnl_usd": 0.75,
            "n_closed": 2,
            "n_opened": 2,
            "n_paper_buy_tags": 2,
        }
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            book_p = tdir / "book.json"
            book_p.write_text(json.dumps(book), encoding="utf-8")
            with mock.patch.object(m, "CRUMBS_PATH", tdir / "c.jsonl"), mock.patch.object(
                m, "BUDGET_PATH", tdir / "b.json"
            ), mock.patch.object(m, "WEEKLY_STATE_PATH", tdir / "w.json"), mock.patch.object(
                m, "WEEKLY_REPORT_PATH", tdir / "w.md"
            ):
                payload = m.build_weekly_rollup(
                    lookback_days=7,
                    now=datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc),
                    write=False,
                    book_path=book_p,
                )
        self.assertEqual(payload["week"]["n_closed"], 1)
        self.assertEqual(payload["week"]["realized_pnl_usd"], 1.25)
        self.assertEqual(payload["week"]["wins"], 1)
        self.assertEqual(payload["week"]["by_pair"].get("ETH-USD"), 1.25)
        self.assertEqual(payload["lifetime"]["n_closed"], 2)


if __name__ == "__main__":
    unittest.main()
