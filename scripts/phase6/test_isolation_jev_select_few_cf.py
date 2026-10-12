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

    def test_collection_gate_soft_buy_opens_tag(self) -> None:
        """Lab default conf_act=0.85 never tags; collection_v1 should."""
        row = {
            "pair": "LINK-USD",
            "ok": True,
            "answers": {
                "action": {"choice": "buy", "confidence": 0.40},
                "should_trade_name_now": {"noul": 0.34},
                "is_fakeout_or_stop_run": {"noul": 0.30},
            },
            "paper": {"paper_would_buy_tag": False, "would_order": False},
        }
        cfg = m.SelectFewConfig()
        gated = m._apply_cf_paper_gate(row, cfg)
        self.assertTrue((gated.get("paper") or {}).get("paper_would_buy_tag"))
        self.assertFalse((gated.get("paper") or {}).get("would_order"))
        # Lab-strict still fails under high conf_act
        strict = m.SelectFewConfig(
            should_trade_min=0.65,
            conf_act=0.85,
            action_conf_min=0.55,
            soft_should_trade_min=0.65,
            soft_action_conf_min=0.55,
            allow_soft_buy_open=False,
        )
        gated_strict = m._apply_cf_paper_gate(row, strict)
        self.assertFalse((gated_strict.get("paper") or {}).get("paper_would_buy_tag"))

    def test_prefer_eligible_over_held_ordering(self) -> None:
        cfg = m.SelectFewConfig(max_pairs=3, prefer_eligible_over_held=True, include_held=True)
        with mock.patch.object(
            m,
            "production_tryout_eligible_sources",
            return_value={"universe": ["AAA-USD", "BBB-USD", "CCC-USD"], "source": "test"},
        ), mock.patch.object(m, "_held_pairs", return_value=["HELD-USD", "HELD2-USD"]):
            pairs, meta = m.resolve_select_universe(cfg)
        self.assertEqual(pairs[0], "AAA-USD")
        self.assertNotIn("HELD-USD", pairs[:2])  # held not first under collection_v1
        self.assertEqual(meta.get("selection_note"), "eligible_first_collection_v1")

    def test_backfill_from_crumbs_opens_seat(self) -> None:
        crumb = {
            "ts": "2026-10-10T12:00:00+00:00",
            "pair": "SOL-USD",
            "ok": True,
            "answers": {
                "action": {"choice": "buy", "confidence": 0.70},
                "should_trade_name_now": {"noul": 0.50},
                "is_fakeout_or_stop_run": {"noul": 0.20},
            },
            "paper": {"paper_would_buy_tag": False},
            "model": "mock",
            "state_compact": {},
        }
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            crumbs = tdir / "crumbs.jsonl"
            crumbs.write_text(json.dumps(crumb) + "\n", encoding="utf-8")
            book_p = tdir / "book.json"
            with mock.patch.object(m, "CRUMBS_PATH", crumbs), mock.patch.object(
                m, "BOOK_PATH", book_p
            ), mock.patch.object(
                m, "load_ohlcv_candles", return_value=[]
            ), mock.patch.object(m, "forward_return", return_value=None):
                out = m.backfill_paper_seats_from_crumbs(
                    cfg=m.SelectFewConfig(write=True, max_open_seats=4),
                    write=True,
                    mark_close=True,
                )
            self.assertGreaterEqual(out["n_gate_pass"], 1)
            self.assertEqual(out["n_opened_now"], 1)
            book = json.loads(book_p.read_text(encoding="utf-8"))
            self.assertEqual(len(book["open"]), 1)
            self.assertEqual(book["open"][0]["pair"], "SOL-USD")
            self.assertFalse(book["open"][0]["would_order"])


if __name__ == "__main__":
    unittest.main()
