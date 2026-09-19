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
        "plans": [
            {
                "status": "planned",
                "pair": "ZEC-USD",
                "step_usd": 25.0,
                "held_usd": 25.0,
                "unrealized_r": 0.01,
                "phase": 2,
                "hold_hours": 3.0,
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
    assert "--apply --go --no-dry-run" in body
    assert "waived" in body.lower()


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
    test_dedupe_blocks_second()
    test_fingerprint_stable()
    print("ALL PASS isolation_tryout_scale_up_live_approval")
