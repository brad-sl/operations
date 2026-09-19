#!/usr/bin/env python3
"""Isolation tests for analyst daily scoreboard + review compose."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _quiet_board(**overrides):
    board = {
        "schema": "analyst_daily_scoreboard_v1",
        "as_of": "2099-01-01T00:00:00Z",
        "trades": {
            "1d": {},
            "3d": {},
            "7d": {"exit_reasons_top": [("rotation_exit", 2)]},
            "30d": {},
        },
        "positions": {},
        "signals": {"basket_n": 11, "signal_counts": {"HOLD": 11}},
        "path": {
            "phase2_ready": False,
            "path_health": "declining",
            "phase2_verdict": "NO-GO",
            "recent_return_pct": 0.1,
            "window_return_pct": -6.8,
        },
        "opt": {
            "deployment_hint": "hold",
            "production_return_pct": -65.0,
            "production_equity_usd": 2300,
            "opt_run_id": "OPT-TEST",
            "opt_winner": "none",
        },
        "pipeline": {
            "active_trials": [],
            "open_review_files": [],
            "strategy_planned": [],
            "proposal_backlog_n": 0,
            "north_star": "test",
            "live_regime": "soft_down",
            "pickup_ready": 0,
            "pickup_running_auto": 0,
        },
        "wounds": {"same_session_3d": {"count_2h": 0, "pairs_2h": []}},
        "gates": {},
        "month_path": {
            "ok": True,
            "current_mtd_return_pct": -0.1,
            "current_mtd_gap_usd": 100.0,
            "current_mtd_process_tax_usd": -4.0,
            "target_monthly_pct": 5.0,
            "hit_rate_closed": 0.0,
            "n_hit": 0,
            "n_miss": 3,
            "n_months_closed": 3,
            "avg_closed_month_return_pct": -20.0,
            "current_leak_counts": {"pile_on": 1},
        },
        "goal": {
            "score_0_100": 0,
            "label": "OFF_TRACK",
            "notes": ["Phase2 exit bar NOT met — stabilize"],
            "north_star": "Consistent ~5%/mo",
            "month_path_mtd_pct": -0.1,
            "month_path_gap_usd": 100.0,
            "month_path_process_tax_usd": -4.0,
            "target_monthly_pct": 5.0,
        },
        "material_flags": ["phase2_not_ready", "path_soft_or_declining"],
        "material": True,
    }
    board.update(overrides)
    return board


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
    assert "stop_loss_exchange" not in body
    assert "operator_unwind_op_missfire" not in body
    assert review.get("schema") == "analyst_daily_review_v3"
    assert review.get("voice") == "management_report_v2_short_delta"
    assert "goal" in review
    assert "tg_deliver" in review
    assert "signal_hash" in review


def test_tg_card_short_and_signal_quiet():
    """Same OFF_TRACK signal twice → second deliver should be silent-eligible."""
    import phase6.research.run_analyst_daily_review as mod

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with mock.patch.object(mod, "STATE", td_path), mock.patch.object(
            mod, "PREV_HASH", td_path / "content_hash.txt"
        ), mock.patch.object(mod, "PREV_SIGNAL", td_path / "signal_hash.txt"), mock.patch.object(
            mod, "OUT_JSON", td_path / "latest.json"
        ), mock.patch.object(mod, "OUT_TXT", td_path / "latest.txt"), mock.patch.object(
            mod, "HISTORY", td_path / "hist.jsonl"
        ), mock.patch.object(mod, "BACKLOG", td_path / "backlog.json"):
            # Live spam case: OFF_TRACK + empty proposals (templates already in backlog).
            with mock.patch.object(mod, "_build_proposals", return_value=[]):
                board = _quiet_board()
                r1 = mod.compose_review(board)
                assert r1.get("proposals") == []
                assert r1["signal_changed"] is True
                assert r1["tg_deliver"] is True
                card = mod.format_tg_card(r1)
                assert "Analyst ·" in card
                assert "OFF_TRACK" in card
                assert "What's working" not in card
                assert "— End of report —" not in card
                assert len(card.splitlines()) <= 14
                # Seed signal hash as if we delivered
                mod.PREV_SIGNAL.write_text(r1["signal_hash"])
                mod.PREV_HASH.write_text(r1["content_hash"])
                r2 = mod.compose_review(board)
                assert r2["signal_changed"] is False
                assert r2["tg_deliver"] is False
                # Tiny float noise inside round-to-1 should not re-page
                board2 = _quiet_board()
                board2["path"]["recent_return_pct"] = 0.14  # still rounds to 0.1
                board2["month_path"]["current_mtd_return_pct"] = -0.06  # rounds to -0.1
                r3 = mod.compose_review(board2)
                assert r3["signal_changed"] is False
                assert r3["tg_deliver"] is False


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
    assert review.get("schema") == "analyst_daily_review_v3"


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
    test_tg_card_short_and_signal_quiet()
    test_quiet_deliver_contract()
    test_human_exit_mix()
    print("OK analyst_daily_review isolation")
