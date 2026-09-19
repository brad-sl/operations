#!/usr/bin/env python3
"""Isolation: Daily Dose Jev ranker shadow (mock, no HTTP, no TG)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_jev_ranker import (  # noqa: E402
    DoseJevConfig,
    compare_lists,
    headline_questions,
    jev_score_from_result,
    mock_answers_for_card,
    run_ranker,
)
from phase6.adapters.judgment_jev import mock_from_fixture  # noqa: E402
from phase6.core.rss_feeds import RssItem  # noqa: E402


class TestDailyDoseJevRanker(unittest.TestCase):
    def test_questions_are_noul(self) -> None:
        q = headline_questions()
        self.assertIn("keep_in_brief", q)
        self.assertEqual(q["noise_or_shill"]["type"], "noul")
        self.assertEqual(len(q), 5)

    def test_score_penalizes_noise(self) -> None:
        clean = mock_from_fixture(
            {
                "keep_in_brief": {"type": "noul", "noul": 0.9, "confidence": 0.8},
                "material_to_book": {"type": "noul", "noul": 0.8, "confidence": 0.8},
                "noise_or_shill": {"type": "noul", "noul": 0.1, "confidence": 0.8},
                "already_priced": {"type": "noul", "noul": 0.1, "confidence": 0.7},
                "coffee_worthy": {"type": "noul", "noul": 0.85, "confidence": 0.7},
            }
        )
        noisy = mock_from_fixture(
            {
                "keep_in_brief": {"type": "noul", "noul": 0.5, "confidence": 0.6},
                "material_to_book": {"type": "noul", "noul": 0.2, "confidence": 0.6},
                "noise_or_shill": {"type": "noul", "noul": 0.95, "confidence": 0.9},
                "already_priced": {"type": "noul", "noul": 0.8, "confidence": 0.7},
                "coffee_worthy": {"type": "noul", "noul": 0.2, "confidence": 0.6},
            }
        )
        sc = jev_score_from_result(clean)["jev_score"]
        sn = jev_score_from_result(noisy)["jev_score"]
        self.assertGreater(sc, sn)

    def test_compare_jaccard(self) -> None:
        a = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        b = [{"id": "2"}, {"id": "3"}, {"id": "4"}]
        c = compare_lists(a, b)
        self.assertEqual(c["n_overlap"], 2)
        self.assertAlmostEqual(c["jaccard"], 2 / 4)

    def test_run_dry_fixture_writes_shadow_only(self) -> None:
        now = datetime(2026, 9, 18, 16, 0, tzinfo=timezone.utc)
        t0 = now - timedelta(hours=2)
        fixture = [
            RssItem(
                title="BlackRock expands Bitcoin ETF inflows as SEC watches",
                summary="Institutional demand rises for BTC products.",
                url="https://example.com/1",
                source="www.coindesk.com",
                source_url="https://www.coindesk.com/rss",
                published=t0,
                feed_url="https://www.coindesk.com/rss",
            ),
            RssItem(
                title="Meme coin OnlyFans researchers raise funds roundup",
                summary="Irrelevant noise story about dogs.",
                url="https://example.com/noise",
                source="decrypt.co",
                source_url="https://decrypt.co/feed",
                published=t0,
                feed_url="https://decrypt.co/feed",
            ),
            RssItem(
                title="Solana outage halts validators for two hours",
                summary="Network halt impacts SOL trading venues.",
                url="https://example.com/sol",
                source="blockworks.co",
                source_url="https://blockworks.co/feed",
                published=t0,
                feed_url="https://blockworks.co/feed",
            ),
            RssItem(
                title="SEC rejects XRP short ETF filing",
                summary="Regulatory decision on XRP product.",
                url="https://example.com/xrp",
                source="www.coindesk.com",
                source_url="https://www.coindesk.com/rss",
                published=t0,
                feed_url="https://www.coindesk.com/rss",
            ),
            RssItem(
                title="What happened in crypto today roundup",
                summary="Daily roundup filler.",
                url="https://example.com/roundup",
                source="cointelegraph.com",
                source_url="https://cointelegraph.com/rss",
                published=t0,
                feed_url="https://cointelegraph.com/rss",
            ),
        ]
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cfg = DoseJevConfig(
                dry_run=True,
                top_n=3,
                max_judge=8,
                baseline_pool=8,
                write_crumbs=True,
                budget_path=tdir / "budget.json",
                crumbs_path=tdir / "crumbs.jsonl",
                latest_path=tdir / "latest.json",
                compare_path=tdir / "compare.md",
                preview_path=tdir / "preview.txt",
            )
            payload = run_ranker(cfg=cfg, fixture_items=fixture)
            self.assertTrue(payload["shadow_only"])
            self.assertFalse(payload["publishes_to_telegram"])
            self.assertFalse(payload["overwrites_daily_dose_latest"])
            self.assertTrue(cfg.latest_path.is_file())
            self.assertTrue(cfg.compare_path.is_file())
            self.assertIn("Jev shadow", cfg.preview_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload.get("jev_top") or []), 1)
            # noise/roundup should not dominate top if mock works
            top_titles = " ".join(x.get("title", "").lower() for x in payload["jev_top"])
            # At least one serious event should rank
            self.assertTrue(
                any(k in top_titles for k in ("blackrock", "solana", "sec", "xrp", "etf", "outage"))
            )
            crumbs = cfg.crumbs_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(crumbs), 3)
            row = json.loads(crumbs[0])
            self.assertIn("jev", row)

    def test_mock_answers_shape(self) -> None:
        a = mock_answers_for_card(
            {"title": "SEC ETF hack", "scores": {"composite": 0.9}}
        )
        self.assertEqual(a["keep_in_brief"]["type"], "noul")


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
