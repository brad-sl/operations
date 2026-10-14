#!/usr/bin/env python3
"""Isolation: plain-language dose summary editorial (dry-run, no HTTP)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_novice_summary import (  # noqa: E402
    POST_DISCLAIMER,
    NoviceSummaryConfig,
    build_prompt,
    format_post,
    mock_summary,
    summarize_cards,
)


class TestPlainSummary(unittest.TestCase):
    def test_prompt_voice_no_novice_label(self) -> None:
        card = {
            "id": "1",
            "title": "Fidelity Adds $438 Million of Bitcoin, Ethereum and Solana",
            "summary": "Asset manager increases crypto holdings across majors.",
            "tickers": ["BTC-USD", "ETH-USD", "SOL-USD"],
        }
        p = build_prompt(card, basket=["BTC-USD", "ETH-USD"], held=["ETH-USD"])
        blob = (p["system"] + "\n" + p["user"]).lower()
        self.assertIn("plain", blob)
        self.assertIn("friendly", blob)
        # Instruction may mention the forbidden word as a negative constraint;
        # the *output* path and user-facing ask must not address the reader as novice.
        self.assertIn("never call the reader a novice", p["system"].lower())
        self.assertNotIn("active novice", p["user"].lower())
        self.assertIn("Fidelity", p["user"])
        self.assertIn("No buy/sell", p["user"])
        self.assertIn("new details only", p["user"].lower())
        self.assertIn("do not restate", p["user"].lower())
        self.assertIn("never restate or paraphrase", p["system"].lower())
        self.assertIn("never end with commentary", p["user"].lower())

    def test_mock_one_paragraph_no_per_card_disclaimer(self) -> None:
        card = {
            "id": "1",
            "title": "Ledger exploit details emerge",
            "summary": "Reports describe how funds moved after a wallet-related incident.",
            "tickers": ["BTC-USD"],
        }
        s = mock_summary(card, basket=["BTC-USD"], held=[])
        self.assertNotIn("…", s)
        self.assertTrue(s.endswith("."))
        self.assertNotIn("\n", s)
        self.assertNotIn("novice", s.lower())
        self.assertNotIn("not a trade", s.lower())
        self.assertNotIn("not investment advice", s.lower())
        self.assertNotIn("keep an eye", s.lower())
        self.assertNotIn("valuable insight", s.lower())
        # Body must not paste the headline
        self.assertNotIn("ledger exploit details emerge", s.lower())

    def test_strip_headline_restatement(self) -> None:
        from phase6.core.daily_dose_novice_summary import _clean_summary_text

        card = {
            "id": "g",
            "title": "Grayscale Buys $20 Million of Solana",
            "summary": (
                "The purchase was allocated to Grayscale's Solana trust product. "
                "Filing notes the add landed in the latest weekly flow report."
            ),
            "tickers": ["SOL-USD"],
        }
        redundant = (
            "Grayscale has purchased $20 million worth of Solana for its ETF. "
            "The fund has recently added this amount to its holdings."
        )
        out = _clean_summary_text(redundant, card=card)
        self.assertNotIn("purchased $20 million worth of solana", out.lower())
        # Should keep or fall through to blurb extras, not empty
        self.assertTrue(len(out) > 20)
        self.assertTrue(out.endswith("."))
        # Trailing "$20M of SOL" restatement after a good detail sentence must die
        mixed = (
            "Grayscale's Solana ETF has recently launched and is already adding to its holdings. "
            "The fund now includes a total of approximately $20 million worth of Solana (SOL)."
        )
        out_m = _clean_summary_text(mixed, card=card)
        self.assertIn("etf", out_m.lower())
        self.assertNotRegex(out_m.lower(), r"\$?20\s*million worth of solana")
        # Same $ figure buried mid-sentence after a real product detail
        buried = (
            "Grayscale's Solana ETF has recently launched and is already seeing significant "
            "investment, with the firm adding approximately $20 million worth of Solana to "
            "its holdings. The ETF is part of Grayscale's broader strategy to expand its "
            "cryptocurrency offerings."
        )
        out_b = _clean_summary_text(buried, card=card)
        self.assertIn("etf", out_b.lower())
        self.assertNotRegex(out_b.lower(), r"\$?20\s*million")
        self.assertNotIn("broader strategy", out_b.lower())
        # Detail-first body that adds product/timing should survive
        detail = (
            "The add was booked into Grayscale's Solana trust product. "
            "Weekly flow filings list the purchase in the latest report."
        )
        out2 = _clean_summary_text(detail, card=card)
        self.assertIn("trust", out2.lower())
        self.assertNotIn("grayscale buys $20 million of solana", out2.lower())

    def test_repair_truncated_lead(self) -> None:
        from phase6.core.daily_dose_novice_summary import _clean_summary_text

        card = {
            "id": "l",
            "title": "Ledger's $93 Million Exploit: Here's What Really Happened",
            "summary": (
                "Here's everything you need to know about the Ledger-related "
                "$92.9 million wallet drain across Bitcoin, Ethereum, TRON, BNB Chain and Polygon."
            ),
            "tickers": ["BTC-USD", "ETH-USD"],
        }
        bad = (
            "9 million from wallets across multiple blockchains, including Bitcoin and Ethereum. "
            "This incident has drawn attention due to the large amount involved."
        )
        out = _clean_summary_text(bad, card=card)
        self.assertNotIn("9 million from wallets", out)
        self.assertNotRegex(out, r"(?i)^9 million")
        self.assertTrue("Ledger" in out or "92.9" in out or "wallet drain" in out.lower())
        self.assertNotIn("drawn attention", out.lower())
        self.assertTrue(out.endswith("."))
        # Decimal amounts must not be sentence-split
        self.assertIn("92.9", out)

    def test_clip_paragraph_keeps_full_sentences(self) -> None:
        from phase6.core.daily_dose_novice_summary import _clip_paragraph

        long = (
            "First sentence stays. Second sentence is also fine. "
            "Third sentence would push over a tight budget and should drop cleanly."
        )
        out = _clip_paragraph(long, 70)
        self.assertTrue(out.endswith("."))
        self.assertNotIn("…", out)
        self.assertIn("First sentence stays.", out)
        self.assertNotIn("Third sentence", out)
    def test_format_post_single_footer_disclaimer(self) -> None:
        items = [
            {
                "title": "Example listing news",
                "tickers": ["ADA-USD"],
                "url": "https://example.com/listing",
                "plain_summary": "A new listing can make a coin easier to access on a major exchange.",
            },
            {
                "title": "Flow news",
                "tickers": ["BTC-USD"],
                "novice_summary": "Large buyers adding bitcoin is a concrete flow story for the day.",
            },
        ]
        post = format_post(items, dose_day="2026-10-10")
        self.assertEqual(post.lower().count("not investment advice"), 1)
        self.assertTrue(post.rstrip().endswith(POST_DISCLAIMER) or POST_DISCLAIMER in post)
        # No per-entry disclaimer echo
        body_only = post.split(POST_DISCLAIMER)[0]
        self.assertNotIn("not a trade signal", body_only.lower())
        # Title hyperlinks when URL present; bare title when missing
        self.assertIn("[Example listing news](https://example.com/listing)", post)
        self.assertIn("2. Flow news", post)
        self.assertNotIn("[Flow news]", post)
    def test_summarize_dry_writes_post(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cfg = NoviceSummaryConfig(
                dry_run=True,
                max_cards=3,
                latest_path=tdir / "plain.json",
                history_path=tdir / "plain_hist.jsonl",
                post_path=tdir / "plain_post.txt",
            )
            cards = [
                {
                    "id": "a",
                    "title": "ETH ETF inflows rise",
                    "summary": "Funds add ether.",
                    "tickers": ["ETH-USD"],
                },
                {
                    "id": "b",
                    "title": "SOL listing news",
                    "tickers": ["SOL-USD"],
                },
            ]
            payload = summarize_cards(
                cards, cfg=cfg, basket=["ETH-USD", "SOL-USD"], held=["ETH-USD"]
            )
            self.assertTrue(payload.get("ok"))
            self.assertTrue(payload.get("shadow_only"))
            self.assertFalse(payload.get("publishes_replacement_dose"))
            self.assertEqual(payload.get("n_items"), 2)
            self.assertEqual(payload.get("disclaimer_placement"), "post_footer_only")
            self.assertTrue(cfg.latest_path.is_file())
            self.assertTrue(cfg.post_path.is_file())
            post = cfg.post_path.read_text(encoding="utf-8")
            self.assertIn(POST_DISCLAIMER, post)
            for it in payload["items"]:
                s = (it.get("plain_summary") or "").lower()
                self.assertTrue(it.get("plain_summary"))
                self.assertNotIn("novice", s)
                self.assertNotIn("not a trade", s)
                self.assertNotIn("keep an eye", s)
                self.assertNotIn("valuable insight", s)

if __name__ == "__main__":
    unittest.main()
