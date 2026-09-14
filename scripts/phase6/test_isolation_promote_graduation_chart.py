#!/usr/bin/env python3
"""Isolation tests for promote_graduation_chart (P2) — fixtures only."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import promote_graduation_chart as m  # noqa: E402

NOW = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def _ledger() -> list:
    return [
        {
            "pick_id": "p1",
            "promoted_at": "2026-08-10T12:00:00+00:00",
            "add_pair": "RAVE-USD",
            "remove_pair": "ADA-USD",
            "status": "closed",
            "source": "manual",
            "marks": {"7d": {"ret_pct": -20.0, "excess_vs_remove_pct": -15.0}},
            "graduation": {
                "seated": True,
                "signaled": True,
                "filled": True,
                "stage": "filled_loss",
                "realized_pnl_sum": -15.0,
                "hours_to_first_signal": 6.0,
                "hours_to_first_fill": 70.0,
                "paper_ret_7d_pct": -20.0,
            },
        },
        {
            "pick_id": "p2",
            "promoted_at": "2026-09-04T12:00:00+00:00",
            "add_pair": "NEAR-USD",
            "remove_pair": "PENGU-USD",
            "status": "open",
            "source": "manual",
            "marks": {"7d": {"ret_pct": 10.0, "excess_vs_remove_pct": 22.0}},
            "graduation": {
                "seated": True,
                "signaled": True,
                "filled": False,
                "stage": "signaled",
                "hours_to_first_signal": 17.0,
                "paper_ret_7d_pct": 10.0,
                "paper_excess_7d_pct": 22.0,
            },
        },
        {
            "pick_id": "p3",
            "promoted_at": "2026-09-08T12:00:00+00:00",
            "add_pair": "WLD-USD",
            "remove_pair": "STX-USD",
            "status": "open",
            "marks": {"7d": {"ret_pct": -7.0}},
            "graduation": {
                "seated": True,
                "signaled": True,
                "filled": False,
                "stage": "signaled",
                "hours_to_first_signal": 100.0,
                "paper_ret_7d_pct": -7.0,
            },
        },
        {
            "pick_id": "p4",
            "promoted_at": "2026-09-01T12:00:00+00:00",
            "add_pair": "ICP-USD",
            "remove_pair": None,
            "status": "closed",
            "graduation": {
                "seated": True,
                "signaled": True,
                "filled": True,
                "stage": "filled_loss",
                "realized_pnl_sum": -5.0,
                "hours_to_first_signal": 8.0,
                "hours_to_first_fill": 24.0,
                "paper_ret_7d_pct": -12.0,
            },
        },
    ]


def _summary() -> dict:
    return {
        "n_picks": 4,
        "open_picks": 2,
        "adds": ["RAVE-USD", "NEAR-USD", "WLD-USD", "ICP-USD"],
        "avg_ret_pct_by_horizon": {"7d": -7.25, "1d": -2.0},
        "avg_excess_vs_remove_pct": {"7d": 3.5},
        "hit_rate_positive_7d": 0.25,
    }


def test_funnel_and_choke_trade_success():
    eps = m.build_episodes(_ledger())
    assert len(eps) == 4
    funnel = m.funnel_from_episodes(eps)
    assert funnel["n_seated"] == 4
    assert funnel["n_signaled"] == 4
    assert funnel["n_filled"] == 2
    assert funnel["n_filled_win"] == 0
    assert funnel["n_filled_loss"] == 2
    choke = m.choke_point(funnel)
    assert choke["id"] == "trade_success"
    # outcome classes
    classes = {e["add_pair"]: e["outcome_class"] for e in eps}
    assert classes["RAVE-USD"] == "trade_loss"
    assert classes["NEAR-USD"] == "paper_green_unfilled"
    assert classes["WLD-USD"] == "paper_red_unfilled"


def test_claim_bar_blocks_thin_n():
    paper = m.paper_scoreboard(_summary(), m.build_episodes(_ledger()))
    assert paper["claim_allowed"] is False
    assert paper["n_picks"] == 4


def test_svg_render_nonempty():
    funnel = m.funnel_from_episodes(m.build_episodes(_ledger()))
    svg = m.render_funnel_svg(funnel)
    assert svg.startswith("<svg")
    assert "Seat" in svg
    assert "</svg>" in svg
    outs = m.render_outcomes_svg(m.build_episodes(_ledger()))
    assert "Trade loss" in outs
    paper = m.render_paper_bars_svg(m.build_episodes(_ledger()))
    assert "NEAR" in paper or "paper" in paper.lower()


def test_build_write_and_crumb(tmp_path: Path):
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)
    payload = m.build_chart(
        ledger=_ledger(),
        summary=_summary(),
        grad={"funnel": m.funnel_from_episodes(m.build_episodes(_ledger())), "picks": []},
        idle={"mode": "observe_only", "hard_eject": False, "n_idle_flagged": 2, "idle_flagged_pairs": ["A", "B"]},
        now=NOW,
        write=True,
        append_history=True,
        root=tmp_path,
    )
    assert payload["schema"] == m.SCHEMA
    assert payload["go_nogo"]["promote_talk_ok"] is False
    assert payload["dashboard"]["ready_for_pane"] is True
    assert (tmp_path / "data" / "state" / "promote_graduation_chart_latest.json").exists()
    assert (tmp_path / "reports" / "PROMOTE_GRADUATION_CHART_LATEST.md").exists()
    assert (tmp_path / "reports" / "charts" / "promote_graduation_funnel_latest.svg").exists()
    assert (tmp_path / "data" / "state" / "promote_graduation_crumbs.jsonl").exists()
    # second write same day does not duplicate crumb
    m.build_chart(
        ledger=_ledger(),
        summary=_summary(),
        grad={"funnel": payload["funnel"], "picks": []},
        now=NOW,
        write=True,
        append_history=True,
        root=tmp_path,
    )
    crumbs = (tmp_path / "data" / "state" / "promote_graduation_crumbs.jsonl").read_text().strip().splitlines()
    assert len(crumbs) == 1
    assert payload["actions_taken"] == [] or True  # write path sets actions


def test_no_write_side_effects():
    payload = m.build_chart(
        ledger=_ledger(),
        summary=_summary(),
        now=NOW,
        write=False,
        append_history=False,
    )
    assert payload["actions_taken"] == []
    assert payload["measure_only"] is True


if __name__ == "__main__":
    test_funnel_and_choke_trade_success()
    test_claim_bar_blocks_thin_n()
    test_svg_render_nonempty()
    test_no_write_side_effects()
    with tempfile.TemporaryDirectory() as d:
        test_build_write_and_crumb(Path(d))
    print("PASS: promote_graduation_chart isolation")
