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


if __name__ == "__main__":
    unittest.main()
