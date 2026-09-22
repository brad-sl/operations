#!/usr/bin/env python3
"""Isolation: scale-up live approval TG card (no money)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import tryout_scale_up_live as live  # noqa: E402


def _plan(**kw):
    base = {
        "live_armed": True,
        "n_planned": 1,
        "signal_bar_profile": "live_signal",
        "signal_bar_gates": {
            "min_hold_hours": 2.0,
            "min_unrealized_r": 0.008,
            "max_unrealized_r": 0.035,
            "require_phase_in": [1, 2],
            "require_structure_ok": True,
            "phase_dwell_bars": 2,
        },
        "plans": [
            {
                "status": "planned",
                "pair": "ZEC-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "unrealized_r": 0.02,
                "phase": 2,
                "hold_hours": 3.0,
                "structure_ok": True,
                "phase_dwell_ok": True,
            }
        ],
        "cf_gate": {"waived": True, "ok": True, "reason": "cf_waived"},
        "safety": {
            "max_steps_per_utc_day": 1,
            "max_step_usd": 25.0,
            "max_usd_per_utc_day": 50.0,
        },
    }
    base.update(kw)
    return base


def test_silent_when_not_armed():
    body = live.approval_telegram_summary(
        _plan(live_armed=False), force=True, mark_sent=False
    )
    assert body == ""


def test_silent_when_no_planned():
    body = live.approval_telegram_summary(
        _plan(n_planned=0, plans=[{"status": "blocked", "pair": "ZEC-USD"}]),
        force=True,
        mark_sent=False,
    )
    assert body == ""


def test_card_when_planned():
    with tempfile.TemporaryDirectory() as td:
        seen = Path(td) / "seen.json"
        with patch.object(live, "APPROVAL_SEEN_PATH", seen), patch.object(
            live, "kill_switch_on", return_value=False
        ), patch.object(
            live,
            "load_decision",
            return_value={
                "cf_bar": {
                    "require": False,
                    "max_waived_steps": 2,
                    "waived_steps_used": 0,
                }
            },
        ):
            body = live.approval_telegram_summary(_plan(), force=True, mark_sent=True)
    assert "SCALE-UP APPROVAL" in body
    assert "ZEC-USD" in body
    assert "+$25" in body
    assert "RECOMMEND:" in body
    assert "Factors:" in body
    assert "HOLD" in body  # CF waived → path-proof hold default
    assert "structure_ok" in body or "struct" in body
    assert "--apply --go --no-dry-run" in body
    assert "waived" in body.lower()


def test_recommend_go_kindling_when_cf_ok():
    plan = _plan(
        cf_gate={"waived": False, "ok": True, "reason": "cf_cleared"},
        plans=[
            {
                "status": "planned",
                "pair": "LINK-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "unrealized_r": 0.018,
                "phase": 1,
                "hold_hours": 4.0,
                "structure_ok": True,
                "phase_dwell_ok": True,
            }
        ],
    )
    rec = live.build_scale_up_recommendation(plan)
    assert rec["label"] == "GO_KINDLING"
    assert "GO kindling" in rec["headline"]
    with patch.object(live, "kill_switch_on", return_value=False), patch.object(
        live,
        "load_decision",
        return_value={"cf_bar": {"require": True, "max_waived_steps": 0}},
    ), patch.object(live, "_append_crumb"):
        body = live.approval_telegram_summary(plan, force=True, mark_sent=False)
    assert "RECOMMEND: GO kindling" in body
    assert "Factors:" in body
    assert "LINK-USD" in body
    assert "phase 1" in body


def test_recommend_hold_when_structure_unknown_soft():
    plan = _plan(
        cf_gate={"waived": False, "ok": True, "reason": "ok"},
        plans=[
            {
                "status": "planned",
                "pair": "ETH-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "unrealized_r": 0.015,
                "phase": 2,
                "hold_hours": 3.0,
                "structure_ok": None,
                "phase_dwell_ok": True,
            }
        ],
    )
    rec = live.build_scale_up_recommendation(plan)
    assert rec["label"] == "HOLD_PATH_PROOF"
    assert any("structure unknown" in x for x in rec["soft_flags"])


def test_dedupe_blocks_second():
    with tempfile.TemporaryDirectory() as td:
        seen = Path(td) / "seen.json"
        with patch.object(live, "APPROVAL_SEEN_PATH", seen), patch.object(
            live, "kill_switch_on", return_value=False
        ), patch.object(
            live,
            "load_decision",
            return_value={"cf_bar": {"require": False, "max_waived_steps": 2}},
        ):
            b1 = live.approval_telegram_summary(_plan(), force=False, mark_sent=True)
            b2 = live.approval_telegram_summary(_plan(), force=False, mark_sent=True)
            b3 = live.approval_telegram_summary(_plan(), force=True, mark_sent=False)
    assert "SCALE-UP APPROVAL" in b1
    assert b2 == ""
    assert "SCALE-UP APPROVAL" in b3


def test_fingerprint_stable():
    fp = live.approval_fingerprint(_plan())
    assert fp == "ZEC-USD:25.00"


if __name__ == "__main__":
    test_silent_when_not_armed()
    test_silent_when_no_planned()
    test_card_when_planned()
    test_recommend_go_kindling_when_cf_ok()
    test_recommend_hold_when_structure_unknown_soft()
    test_dedupe_blocks_second()
    test_fingerprint_stable()
    print("ALL PASS isolation_tryout_scale_up_live_approval")
