#!/usr/bin/env python3
"""Isolation tests for regime_arm_switch_metrics (P3)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import regime_arm_switch_metrics as m  # noqa: E402

NOW = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def _crumbs():
    return [
        {
            "ts": "2026-09-12T18:36:11+00:00",
            "preferred_arm": "risk_adj_mom",
            "changed": True,
            "decision_written": True,
            "sticky_tape": "btc_down",
            "raw_tape": "btc_down",
            "btc_ret_7d_pct": -3.4,
        },
        {
            "ts": "2026-09-13T18:40:00+00:00",
            "preferred_arm": "risk_adj_mom",
            "changed": False,
            "decision_written": True,
            "sticky_tape": "btc_down",
            "btc_ret_7d_pct": -3.7,
        },
        {
            "ts": "2026-09-14T18:41:00+00:00",
            "preferred_arm": "rel_btc_stable",
            "changed": True,
            "decision_written": True,
            "sticky_tape": "btc_chop",
            "btc_ret_7d_pct": -0.05,
        },
    ]


def _daily():
    # synthetic closes spanning flip days + forward
    base = 80000.0
    days = []
    # Sep 10-20
    prices = {
        "2026-09-10": 81000,
        "2026-09-11": 80000,
        "2026-09-12": 78000,  # flip to ram
        "2026-09-13": 77000,
        "2026-09-14": 79000,  # flip to rel
        "2026-09-15": 79200,
        "2026-09-16": 79500,
        "2026-09-17": 80000,
        "2026-09-18": 80500,
        "2026-09-19": 81000,
        "2026-09-20": 81200,
        "2026-09-21": 81500,
    }
    for d, c in prices.items():
        days.append({"day": d, "close": float(c)})
    return days


def _board():
    return {
        "arms": [
            {
                "arm": "rel_btc_stable",
                "ex7": 5.0,
                "hit7": 0.55,
                "n7": 40,
                "sleeve_delta": 10.0,
                "high_confidence": True,
                "missing": [],
            },
            {
                "arm": "risk_adj_mom",
                "ex7": 1.0,
                "hit7": 0.45,
                "n7": 40,
                "sleeve_delta": -5.0,
                "high_confidence": False,
                "missing": ["ex7"],
            },
        ]
    }


def test_extract_flips():
    flips = m.extract_flip_events(_crumbs())
    assert len(flips) == 2
    assert flips[0]["preferred_arm"] == "risk_adj_mom"
    assert flips[1]["preferred_arm"] == "rel_btc_stable"


def test_score_and_claim_thin():
    daily = _daily()
    eps = [m.score_flip_forward(f, daily) for f in m.extract_flip_events(_crumbs())]
    assert len(eps) == 2
    # first flip 9/12 has forward data
    assert eps[0].get("complete_3d") is True
    summ = m.summarize_episodes(eps)
    assert summ["n_flips"] == 2
    assert summ["claim_allowed"] is False  # thin N


def test_hc_compare():
    cmp = m.compare_arms_hc(_board(), "rel_btc_stable")
    assert cmp["ex7_leader"] == "rel_btc_stable"
    assert cmp["preferred_is_hc"] is True


def test_build_write(tmp_path: Path):
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)
    (tmp_path / "data" / "ohlcv").mkdir(parents=True)
    payload = m.build_metrics(
        crumbs=_crumbs(),
        board=_board(),
        daily=_daily(),
        switch_latest={
            "preferred_arm": "rel_btc_stable",
            "sticky_tape": "btc_chop",
            "btc_ret_7d_pct": -0.05,
            "flipped": True,
        },
        now=NOW,
        write=True,
        append_history=True,
        root=tmp_path,
    )
    assert payload["schema"] == m.SCHEMA
    assert payload["go_nogo"]["live_swaps"] is False
    assert payload["measure_only"] is True
    assert (tmp_path / "data/state/regime_arm_switch_metrics_latest.json").exists()
    assert (tmp_path / "reports/charts/regime_arm_switch_timeline_latest.svg").exists()
    assert payload["dashboard"]["ready_for_pane"] is True


def test_svg_ok():
    svg = m.render_timeline_svg([])
    assert "<svg" in svg
    svg2 = m.render_compare_svg(m.compare_arms_hc(_board(), "rel_btc_stable"))
    assert "pref ex7" in svg2


if __name__ == "__main__":
    test_extract_flips()
    test_score_and_claim_thin()
    test_hc_compare()
    test_svg_ok()
    with tempfile.TemporaryDirectory() as d:
        test_build_write(Path(d))
    print("PASS: regime_arm_switch_metrics isolation")
