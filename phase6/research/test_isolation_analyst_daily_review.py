#!/usr/bin/env python3
"""Isolation tests for analyst daily scoreboard + review compose."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_scoreboard_builds():
    from phase6.research.analyst_daily_scoreboard import build_scoreboard, format_scoreboard_md

    board = build_scoreboard()
    assert board.get("schema") == "analyst_daily_scoreboard_v1"
    assert "goal" in board
    assert "trades" in board and "1d" in board["trades"]
    assert "pipeline" in board
    assert "material_flags" in board
    md = format_scoreboard_md(board)
    assert "GOAL:" in md
    assert "Analyst Daily Scoreboard" in md


def test_review_sections():
    from phase6.research.analyst_daily_scoreboard import build_scoreboard
    from phase6.research.run_analyst_daily_review import compose_review, format_review_text

    board = build_scoreboard()
    review = compose_review(board)
    body = format_review_text(review)
    for sec in (
        "Goal realization",
        "What's working",
        "What's not",
        "What needs to change",
        "Pipeline",
        "Results of recent changes",
        "Blockers",
        "Needs your call",
    ):
        assert sec in body, f"missing section {sec}"
    # no raw tuple dump of exit reasons
    assert "stop_loss_exchange" not in body
    assert "operator_unwind_op_missfire" not in body
    assert review.get("schema") == "analyst_daily_review_v2"
    assert review.get("voice") == "management_report_v1"
    assert "goal" in review


def test_quiet_deliver_contract():
    """--deliver with forced ON_TRACK + no proposals can be non-material."""
    from phase6.research.run_analyst_daily_review import compose_review, format_review_text

    board = {
        "schema": "analyst_daily_scoreboard_v1",
        "as_of": "2099-01-01T00:00:00Z",
        "trades": {"1d": {}, "3d": {}, "7d": {}, "30d": {}},
        "positions": {},
        "signals": {"basket_n": 11, "signal_counts": {"HOLD": 11}},
        "path": {"phase2_ready": True, "path_health": "stable", "phase2_verdict": "GO"},
        "opt": {
            "deployment_hint": "hold",
            "production_return_pct": 5.0,
            "production_equity_usd": 10000,
        },
        "pipeline": {
            "active_trials": [],
            "open_review_files": [],
            "strategy_planned": [],
            "proposal_backlog_n": 0,
            "north_star": "test",
            "live_regime": "bull",
        },
        "wounds": {"same_session_3d": {"count_2h": 0, "pairs_2h": []}},
        "gates": {},
        "goal": {
            "score_0_100": 80,
            "label": "ON_TRACK",
            "notes": ["ok"],
            "north_star": "test",
        },
        "material_flags": ["quiet_stable"],
        "material": False,
    }
    review = compose_review(board)
    body = format_review_text(review)
    assert "Goal realization: ON_TRACK" in body
    assert review.get("content_hash")


def test_human_exit_mix():
    from phase6.research.run_analyst_daily_review import _human_exit_mix

    s = _human_exit_mix(
        [
            ("stop_loss_exchange", 3),
            ("dust_sweep_after_sl", 2),
            ("operator_unwind_op_missfire_Brad_GO_C_20260901", 1),
        ]
    )
    assert "stop-loss" in s
    assert "dust cleanup" in s
    assert "operator unwind" in s
    assert "[" not in s
    assert "stop_loss_exchange" not in s


if __name__ == "__main__":
    test_scoreboard_builds()
    test_review_sections()
    test_quiet_deliver_contract()
    print("OK analyst_daily_review isolation")
