#!/usr/bin/env python3
"""Isolation: Jev lab packet + mock port + paper gate (no live HTTP required)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.adapters.judgment_jev import mock_from_fixture, parse_answers  # noqa: E402
from phase6.core.jev_lab_shadow import LabConfig, run_lab  # noqa: E402
from phase6.domain.ports.judgment import JudgmentResult  # noqa: E402
from phase6.domain.services.decision_packet import (  # noqa: E402
    build_pair_state,
    confidence_gate_paper,
    default_lab_questions,
)


class TestPacket(unittest.TestCase):
    def test_questions_atomic(self):
        q = default_lab_questions()
        self.assertIn("action", q)
        self.assertEqual(q["action"]["type"], "choice")
        self.assertEqual(q["is_fakeout_or_stop_run"]["type"], "noul")
        self.assertEqual(q["setup_quality"]["type"], "score")

    def test_state_builds(self):
        st = build_pair_state("BTC-USD")
        self.assertEqual(st["pair"], "BTC-USD")
        self.assertIn("indicators", st)
        self.assertIn("inventory", st)


class TestParseAndGate(unittest.TestCase):
    def test_parse_answers(self):
        payload = {
            "answers": {
                "should_trade_name_now": {"type": "noul", "noul": 0.8},
                "action": {
                    "type": "choice",
                    "choice": "buy",
                    "confidence": 0.9,
                    "probabilities": {"buy": 0.9, "hold": 0.1},
                },
                "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.2},
            }
        }
        ans = parse_answers(payload)
        self.assertAlmostEqual(ans["should_trade_name_now"].noul or 0, 0.8)
        self.assertEqual(ans["action"].choice, "buy")
        g = confidence_gate_paper(ans)
        self.assertTrue(g["paper_would_buy_tag"])
        self.assertFalse(g["would_order"])

    def test_gate_blocks_fakeout(self):
        ans = parse_answers(
            {
                "answers": {
                    "should_trade_name_now": {"type": "noul", "noul": 0.9},
                    "action": {"type": "choice", "choice": "buy", "confidence": 0.9},
                    "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.8},
                }
            }
        )
        g = confidence_gate_paper(ans)
        self.assertFalse(g["paper_would_buy_tag"])


class FakePort:
    def decide(self, state, questions, *, model=None):
        return mock_from_fixture(
            {
                "action": {"type": "choice", "choice": "hold", "confidence": 0.6},
                "regime": {"type": "choice", "choice": "range", "confidence": 0.5},
                "setup_quality": {"type": "score", "score": 1.0, "confidence": 0.5},
                "is_fakeout_or_stop_run": {"type": "noul", "noul": 0.3},
                "should_trade_name_now": {"type": "noul", "noul": 0.2},
            },
            model=model or "fake",
        )


class TestRunLab(unittest.TestCase):
    def test_dry_run_and_port(self):
        tmp = tempfile.TemporaryDirectory()
        tdir = Path(tmp.name)
        cfg = LabConfig(
            pairs=["BTC-USD"],
            dry_run=False,
            write_crumbs=True,
            budget_path=tdir / "budget.json",
            crumbs_path=tdir / "crumbs.jsonl",
            latest_path=tdir / "latest.json",
            max_calls_per_day=10,
        )
        # inject port so no HTTP; budget still increments on ok
        s = run_lab(cfg=cfg, port=FakePort(), pairs=["BTC-USD"])
        self.assertEqual(s["n_ok"], 1)
        self.assertFalse(s["results"][0]["would_order"])
        self.assertTrue((tdir / "latest.json").is_file())
        tmp.cleanup()

    def test_dry_run_flag_no_budget(self):
        tmp = tempfile.TemporaryDirectory()
        tdir = Path(tmp.name)
        cfg = LabConfig(
            pairs=["ETH-USD"],
            dry_run=True,
            write_crumbs=True,
            budget_path=tdir / "budget.json",
            crumbs_path=tdir / "crumbs.jsonl",
            latest_path=tdir / "latest.json",
        )
        s = run_lab(cfg=cfg)
        self.assertEqual(s["n_ok"], 1)
        self.assertTrue(s["dry_run"])
        # dry_run mock path does not increment budget
        b = json.loads((tdir / "budget.json").read_text()) if (tdir / "budget.json").is_file() else {"calls": 0}
        # budget file may not exist until live ok
        self.assertEqual(int(b.get("calls") or 0), 0)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
