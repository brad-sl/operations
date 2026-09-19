#!/usr/bin/env python3
"""Isolation: locked-pool Daily Dose A/B (mock Jev, no HTTP, no TG replace)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_jev_ab import (  # noqa: E402
    DoseAbConfig,
    build_relevance_notes,
    classify_card,
    load_freeze_pool,
    run_locked_ab,
)


def _card(iid: str, title: str, tickers: list[str], comp: float = 0.5) -> dict:
    return {
        "id": iid,
        "title": title,
        "tickers": tickers,
        "primary_pair": (tickers[0] + "-USD") if tickers else None,
        "scores": {"composite": comp},
        "url": f"https://example.com/{iid}",
        "source": "example.com",
    }


class TestDailyDoseJevAb(unittest.TestCase):
    def test_freeze_includes_arm_a(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            draft = tdir / "draft.json"
            a = [_card("a1", "ETH ETF inflows rise", ["ETH"], 0.9)]
            draft.write_text(
                json.dumps({"items": [_card("d1", "Other SOL news", ["SOL"], 0.4)]}),
                encoding="utf-8",
            )
            pool = load_freeze_pool(draft, a, max_n=10)
            ids = {str(c["id"]) for c in pool}
            self.assertIn("a1", ids)
            self.assertIn("d1", ids)

    def test_classify_theater_vs_flow(self) -> None:
        th = classify_card(
            _card("1", "Millions of XRP shorts get liquidated as price surges", ["XRP"]),
            basket=["XRP-USD", "ETH-USD"],
            held=[],
        )
        fl = classify_card(
            _card("2", "Ethereum ETFs add inflows as Fidelity leads flows", ["ETH"]),
            basket=["XRP-USD", "ETH-USD"],
            held=[],
        )
        self.assertIn("theater", th["tags"])
        self.assertIn("flow_macro", fl["tags"])
        self.assertGreater(fl["desk_relevance_0_3"], th["desk_relevance_0_3"])

    def test_run_locked_dry_fixture(self) -> None:
        arm_a = [
            _card("1", "Ethereum ETFs add $29M as Fidelity leads flows", ["ETH"], 0.9),
            _card("2", "Vitalik argues that local AI can protect privacy", ["ETH"], 0.7),
            _card("3", "XRP shorts get liquidated as price surges to $1.4", ["XRP"], 0.6),
            _card("4", "Solana rockets to $112 as volume hits highs", ["SOL"], 0.55),
            _card("5", "Layer-2 tokens lead advance as Fed nerves fade", ["ARB"], 0.5),
        ]
        freeze = arm_a + [
            _card("6", "Hyperliquid launches manual borrowing upgrade", ["HYPE"], 0.45),
            _card("7", "Ripple payments upgrade for asset managers", ["XRP"], 0.4),
            _card("8", "Cardano YouTube scam alert roundup", ["ADA"], 0.35),
        ]
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cfg = DoseAbConfig(
                dry_run=True,
                top_n=5,
                max_judge=8,
                latest_path=tdir / "ab.json",
                card_path=tdir / "ab.md",
                history_path=tdir / "ab_hist.jsonl",
                edited_path=tdir / "edited.json",  # unused with fixtures
                draft_path=tdir / "draft.json",
            )
            # crumbs/budget under tmp via judge_pool defaults — patch by env not needed;
            # DoseJevConfig still writes to real crumbs unless we pass port-only dry.
            # Use fixture paths: monkey via writing empty and accepting project crumbs is OK
            # for isolation of AB logic; mock has no HTTP.
            payload = run_locked_ab(
                cfg=cfg,
                fixture_arm_a=arm_a,
                fixture_freeze=freeze,
            )
            self.assertTrue(payload.get("ok"))
            self.assertFalse(payload.get("publishes_replacement_dose"))
            self.assertEqual(len(payload.get("arm_a") or []), 5)
            self.assertEqual(len(payload.get("arm_b") or []), 5)
            # Freeze must include published ids
            freeze_ids = set(payload.get("freeze_ids") or [])
            for c in arm_a:
                self.assertIn(c["id"], freeze_ids)
            self.assertTrue(cfg.card_path.is_file())
            card = cfg.card_path.read_text(encoding="utf-8")
            self.assertIn("A — published", card)
            self.assertIn("B — Jev", card)
            self.assertIn("NOT a trade signal", card)
            # History row
            self.assertTrue(cfg.history_path.is_file())
            # TG card is short, not full second dose branding
            tg = payload.get("tg_card") or ""
            self.assertIn("locked freeze", tg)
            self.assertIn("NOT a second dose", tg)

    def test_relevance_notes_shape(self) -> None:
        a = [_card("1", "ETF flows", ["ETH"]), _card("2", "scam roundup", ["ADA"])]
        b = [_card("1", "ETF flows", ["ETH"]), _card("3", "upgrade launch", ["HYPE"])]
        cmp_ = {
            "only_baseline": ["2"],
            "only_jev": ["3"],
            "n_overlap": 1,
            "n_baseline": 2,
            "jaccard": 0.33,
        }
        idx = {c["id"]: c for c in a + b}
        rel = build_relevance_notes(
            a, b, cmp_, basket=["ETH-USD", "HYPE-USD", "ADA-USD"], held=[], id_index=idx
        )
        self.assertIn(rel["auto_mark"], ("b_better", "a_better", "mixed"))
        self.assertTrue(rel["move_notes"])
        self.assertIsNone(rel["brad_mark"])


if __name__ == "__main__":
    unittest.main()
