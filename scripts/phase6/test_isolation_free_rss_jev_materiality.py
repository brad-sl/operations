#!/usr/bin/env python3
"""Isolation: Free/RSS Jev materiality shadow (mock, no HTTP, no live cache)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.adapters.judgment_jev import mock_from_fixture, parse_answers
from phase6.core.free_rss_jev_materiality import (
    FreeJevConfig,
    HeadlineObs,
    jev_weight_from_result,
    materiality_questions,
    merge_free_hybrid_jev,
    run_free_rss_jev,
    score_pairs_from_obs,
    select_for_judge,
)
from phase6.domain.ports.judgment import JudgmentResult


class _FixedPort:
    def __init__(self, answers: dict) -> None:
        self._answers = answers

    def decide(self, state, questions, **kwargs):  # noqa: ANN001
        return mock_from_fixture(self._answers)


class TestFreeRssJev(unittest.TestCase):
    def test_questions_schema_has_true_false_criteria(self):
        q = materiality_questions()
        for name, body in q.items():
            self.assertEqual(body.get("type"), "noul", name)
            self.assertIn("instructions", body, name)
            crit = body.get("criteria") or {}
            self.assertIn("true", crit, name)
            self.assertIn("false", crit, name)

    def test_noise_lowers_weight(self):
        good2 = JudgmentResult(
            ok=True,
            model="t",
            answers=parse_answers(
                {
                    "answers": {
                        "material_to_book": {"type": "noul", "noul": 0.9},
                        "noise_or_shill": {"type": "noul", "noul": 0.1},
                        "already_priced": {"type": "noul", "noul": 0.1},
                        "durable_vs_spike": {"type": "noul", "noul": 0.8},
                    }
                }
            ),
        )
        bad2 = JudgmentResult(
            ok=True,
            model="t",
            answers=parse_answers(
                {
                    "answers": {
                        "material_to_book": {"type": "noul", "noul": 0.2},
                        "noise_or_shill": {"type": "noul", "noul": 0.9},
                        "already_priced": {"type": "noul", "noul": 0.8},
                        "durable_vs_spike": {"type": "noul", "noul": 0.2},
                    }
                }
            ),
        )
        wg = jev_weight_from_result(good2)["jev_weight"]
        wb = jev_weight_from_result(bad2)["jev_weight"]
        self.assertGreater(wg, wb)
        self.assertGreater(wg, 0.4)
        self.assertLess(wb, 0.25)

    def test_score_pairs_downweights_noise(self):
        obs = [
            HeadlineObs(
                title="BlackRock ETH ETF inflows $1B",
                text="BlackRock ETH ETF inflows $1B",
                published=None,
                polarity=0.5,
                recency_w=1.0,
                pairs=["ETH-USD"],
                uid="good",
            ),
            HeadlineObs(
                title="10 coins to explode this week!!!",
                text="10 coins to explode this week!!!",
                published=None,
                polarity=0.5,
                recency_w=1.0,
                pairs=["ETH-USD"],
                uid="junk",
            ),
        ]
        scores = score_pairs_from_obs(
            obs, {"good": 1.2, "junk": 0.08}, basket=["ETH-USD"]
        )
        scores_equal = score_pairs_from_obs(
            obs, {"good": 1.0, "junk": 1.0}, basket=["ETH-USD"]
        )
        self.assertGreater(scores["ETH-USD"]["sentiment"], 0.0)
        self.assertGreater(scores["ETH-USD"]["weight_sum"], 0.5)
        self.assertNotEqual(
            scores["ETH-USD"]["weight_sum"], scores_equal["ETH-USD"]["weight_sum"]
        )

    def test_select_prefers_strong_obs(self):
        obs = [
            HeadlineObs("a", "a", None, 0.1, 0.2, ["BTC-USD"], "weak"),
            HeadlineObs("b", "b", None, 0.8, 1.0, ["BTC-USD", "ETH-USD"], "strong"),
        ]
        top = select_for_judge(obs, 1)
        self.assertEqual(top[0].uid, "strong")

    def test_hybrid_merge_uses_jev_text(self):
        rss_jev = {
            "BTC-USD": {
                "sentiment": 0.4,
                "post_count": 2,
                "judged_hits": 1,
                "confidence": 0.5,
            }
        }
        out = merge_free_hybrid_jev(
            rss_jev,
            basket=["BTC-USD"],
            funding={},
            fng={"score_damped": 0.0},
        )
        self.assertAlmostEqual(out["BTC-USD"]["sentiment_score"], 0.4, places=3)
        self.assertEqual(out["BTC-USD"]["source"], "rss_jev")

    def test_run_dry_mock_no_live_write(self):
        live = ROOT / "data" / "state" / "sentiment_cache.json"
        before = live.read_bytes() if live.is_file() else b""
        obs = [
            HeadlineObs(
                title="SEC approves spot ETF expansion",
                text="SEC approves spot ETF expansion for ETH",
                published=None,
                polarity=0.4,
                recency_w=1.0,
                pairs=["ETH-USD", "BTC-USD"],
                uid="etf",
            ),
            HeadlineObs(
                title="You won't believe this moonshot",
                text="You won't believe this moonshot coin",
                published=None,
                polarity=0.6,
                recency_w=1.0,
                pairs=["DOGE-USD"],
                uid="moon",
            ),
        ]
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            cfg = FreeJevConfig(
                dry_run=True,
                max_judge=5,
                write_crumbs=False,
                budget_path=tdp / "budget.json",
                crumbs_path=tdp / "crumbs.jsonl",
                latest_path=tdp / "latest.json",
                compare_path=tdp / "compare.md",
                rss_jev_path=tdp / "rss_jev.json",
                free_jev_path=tdp / "free_jev.json",
            )
            port = _FixedPort(
                {
                    "material_to_book": {"type": "noul", "noul": 0.7},
                    "noise_or_shill": {"type": "noul", "noul": 0.2},
                    "already_priced": {"type": "noul", "noul": 0.2},
                    "durable_vs_spike": {"type": "noul", "noul": 0.6},
                }
            )
            result = run_free_rss_jev(port=port, cfg=cfg, obs_override=obs)
            self.assertTrue(result.get("ok"))
            meta = result.get("meta") or {}
            self.assertIs(meta.get("would_write_live_sentiment"), False)
            self.assertGreaterEqual(int(meta.get("n_judged") or 0), 1)
        after = live.read_bytes() if live.is_file() else b""
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
