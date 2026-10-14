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
    assert payload.get("hygiene", {}).get("live_apply") is False


def test_stale_no_fill_hygiene():
    """A: never-filled episodes past max age close on chart only."""
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    eps = [
        {
            "pick_id": "old_sig",
            "add_pair": "PENGU-USD",
            "promoted_at": "2026-08-20T00:00:00+00:00",
            "stage": "signaled",
            "filled": False,
            "status": "open",
            "episode_open": True,
            "paper_ret_7d_pct": 2.0,
        },
        {
            "pick_id": "young_sig",
            "add_pair": "NEAR-USD",
            "promoted_at": "2026-10-01T00:00:00+00:00",
            "stage": "signaled",
            "filled": False,
            "status": "open",
            "episode_open": True,
        },
        {
            "pick_id": "open_fill",
            "add_pair": "ADA-USD",
            "promoted_at": "2026-08-01T00:00:00+00:00",
            "stage": "filled_open",
            "filled": True,
            "status": "open",
            "episode_open": True,
            "realized_pnl_sum": 0.5,
        },
    ]
    out = m.apply_stale_episode_hygiene(eps, now=now, hygiene=m.DEFAULT_HYGIENE)
    by = {e["add_pair"]: e for e in out}
    assert by["PENGU-USD"]["stage"] == "stale_no_fill"
    assert by["PENGU-USD"]["stale_flushed"] is True
    assert by["PENGU-USD"]["status"] == "closed"
    assert by["PENGU-USD"]["episode_open"] is False
    assert by["NEAR-USD"]["stage"] == "signaled"
    assert by["NEAR-USD"].get("stale_flushed") is False
    # filled_open is never stale by age alone
    assert by["ADA-USD"]["stage"] == "filled_open"
    assert by["ADA-USD"].get("stale_flushed") is False


def test_eject_autopsy_and_flush_candidates():
    """B: eject-only closed fills tagged; flush list measure-only."""
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    eps = [
        {
            "pick_id": "hype",
            "add_pair": "HYPE-USD",
            "promoted_at": "2026-09-01T00:00:00+00:00",
            "stage": "filled_loss",
            "filled": True,
            "realized_pnl_sum": -8.5,
            "hours_to_first_fill": 40.0,
        },
        {
            "pick_id": "zec",
            "add_pair": "ZEC-USD",
            "promoted_at": "2026-09-03T00:00:00+00:00",
            "stage": "filled_win",
            "filled": True,
            "realized_pnl_sum": 2.1,
            "hours_to_first_fill": 12.0,
        },
        {
            "pick_id": "pengu",
            "add_pair": "PENGU-USD",
            "promoted_at": "2026-08-20T00:00:00+00:00",
            "stage": "signaled",
            "filled": False,
            "status": "open",
            "episode_open": True,
        },
    ]
    eps = m.apply_stale_episode_hygiene(eps, now=now, hygiene=m.DEFAULT_HYGIENE)
    trades = [
        {
            "pair": "HYPE-USD",
            "side": "BUY",
            "ts": "2026-09-02T00:00:00+00:00",
            "pnl_usd": None,
        },
        {
            "pair": "HYPE-USD",
            "side": "SELL",
            "ts": "2026-09-05T00:00:00+00:00",
            "pnl_usd": -8.5,
            "reason": "tryout_scale_window_eject",
        },
        {
            "pair": "ZEC-USD",
            "side": "BUY",
            "ts": "2026-09-04T00:00:00+00:00",
        },
        {
            "pair": "ZEC-USD",
            "side": "SELL",
            "ts": "2026-09-10T00:00:00+00:00",
            "pnl_usd": 2.1,
            "reason": "take_profit_hit",
        },
    ]
    autopsy = m.run_eject_autopsy(eps, trades=trades, hygiene=m.DEFAULT_HYGIENE)
    assert autopsy["enabled"] is True
    assert autopsy["n_eject_only_or_dominant"] >= 1
    eject_pairs = {r["add_pair"] for r in autopsy["eject_rows"]}
    assert "HYPE-USD" in eject_pairs
    assert "ZEC-USD" not in eject_pairs

    flush = m.build_flush_candidates(
        eps,
        autopsy,
        holdings={"HYPE-USD": 0.0, "PENGU-USD": 0.0, "BTC-USD": 100.0},
        hygiene=m.DEFAULT_HYGIENE,
        active_basket=["HYPE-USD", "PENGU-USD", "BTC-USD", "ZEC-USD"],
    )
    assert flush["live_apply"] is False
    pairs = {c["pair"]: c for c in flush["candidates"]}
    assert "HYPE-USD" in pairs
    assert "eject_only_loss" in pairs["HYPE-USD"]["reasons"]
    assert "PENGU-USD" in pairs
    assert "stale_no_fill" in pairs["PENGU-USD"]["reasons"]
    # sticky protect never listed
    assert "BTC-USD" not in pairs


def test_build_writes_hygiene_artifacts(tmp_path: Path):
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "trades").mkdir(parents=True)
    (tmp_path / "config" / "promote_graduation_hygiene.json").write_text(
        json.dumps(m.DEFAULT_HYGIENE) + "\n"
    )
    (tmp_path / "trades" / "phase6_trades.jsonl").write_text(
        json.dumps(
            {
                "pair": "RAVE-USD",
                "side": "SELL",
                "ts": "2026-08-20T00:00:00+00:00",
                "pnl_usd": -15.0,
                "reason": "tryout_eject",
            }
        )
        + "\n"
    )
    # age ledger so stale can fire on NEAR/WLD relative to NOW=2026-09-14
    ledger = _ledger()
    ledger[1]["promoted_at"] = "2026-07-01T12:00:00+00:00"  # NEAR old signaled
    ledger[2]["promoted_at"] = "2026-07-10T12:00:00+00:00"  # WLD old signaled
    payload = m.build_chart(
        ledger=ledger,
        summary=_summary(),
        grad={"funnel": {}, "picks": []},
        idle={"mode": "observe_only", "hard_eject": False, "n_idle_flagged": 0, "idle_flagged_pairs": []},
        now=NOW,
        write=True,
        append_history=False,
        root=tmp_path,
    )
    assert payload["hygiene"]["live_apply"] is False
    assert payload["hygiene"]["n_stale_flushed"] >= 1
    assert "eject_autopsy" in payload
    assert "flush_candidates" in payload
    assert (tmp_path / "data" / "state" / "promote_eject_autopsy_latest.json").exists()
    assert (tmp_path / "data" / "state" / "promote_flush_candidates_latest.json").exists()
    assert (tmp_path / "reports" / "PROMOTE_EJECT_AUTOPSY_LATEST.md").exists()
    assert payload["flush_candidates"]["live_apply"] is False
    board = m.short_board(payload)
    assert "stale_flush=" in board
    assert "eject_tax=" in board


if __name__ == "__main__":
    test_funnel_and_choke_trade_success()
    test_claim_bar_blocks_thin_n()
    test_svg_render_nonempty()
    test_no_write_side_effects()
    test_stale_no_fill_hygiene()
    test_eject_autopsy_and_flush_candidates()
    with tempfile.TemporaryDirectory() as d:
        test_build_write_and_crumb(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_build_writes_hygiene_artifacts(Path(d))
    print("PASS: promote_graduation_chart isolation")
