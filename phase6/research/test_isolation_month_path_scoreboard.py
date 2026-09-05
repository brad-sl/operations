#!/usr/bin/env python3
"""Isolation: month-path scoreboard (~5%/mo gap + process tax)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_build_and_persist():
    from phase6.research.month_path_scoreboard import (
        SCHEMA,
        TARGET_MONTHLY_PCT,
        analyst_snippet,
        build_month_path,
        format_month_path_md,
        persist,
    )

    board = build_month_path(months_back=6)
    assert board.get("schema") == SCHEMA
    assert board.get("target_monthly_pct") == TARGET_MONTHLY_PCT
    assert board.get("edge_class")
    assert "summary" in board
    assert "months" in board
    assert board.get("sensor", {}).get("ok") is True
    md = format_month_path_md(board)
    assert "Month-path scoreboard" in md
    assert "5%" in md or "5.0" in md
    persist(board, md)
    snip = analyst_snippet(board)
    assert snip.get("ok") is True
    assert snip.get("target_monthly_pct") == TARGET_MONTHLY_PCT
    print("PASS test_build_and_persist")


def test_scoreboard_includes_month_path():
    from phase6.research.analyst_daily_scoreboard import build_scoreboard, format_scoreboard_md

    board = build_scoreboard()
    assert "month_path" in board
    mp = board["month_path"]
    assert mp.get("ok") is True or mp.get("error")
    g = board.get("goal") or {}
    assert "target_monthly_pct" in g or g.get("north_star")
    md = format_scoreboard_md(board)
    assert "Month path" in md or "month path" in md.lower() or "5%" in md
    print("PASS test_scoreboard_includes_month_path")


def test_review_mentions_month_path_when_present():
    from phase6.research.analyst_daily_scoreboard import build_scoreboard
    from phase6.research.run_analyst_daily_review import compose_review, format_review_text

    board = build_scoreboard()
    review = compose_review(board)
    body = format_review_text(review)
    assert "Goal realization" in body
    # month_path block should surface in not_working or goal notes path
    assert review.get("month_path") is not None
    if (board.get("month_path") or {}).get("ok"):
        blob = body.lower() + " " + " ".join(str(x).lower() for x in (review.get("not_working") or []))
        assert "month-path" in blob or "5%" in blob or "process tax" in blob
    print("PASS test_review_mentions_month_path_when_present")


if __name__ == "__main__":
    test_build_and_persist()
    test_scoreboard_includes_month_path()
    test_review_mentions_month_path_when_present()
    print("OK month_path isolation")
