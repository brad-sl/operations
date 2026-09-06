#!/usr/bin/env python3
"""Isolation: short_gate_label + recovery summary for Signals telegraph.

Run: PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_gate_label_signals.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.dashboard_serve_helpers import (  # noqa: E402
    recovery_policy_dashboard_summary,
    short_gate_label,
)


def test_short_gate_label_maps():
    assert short_gate_label(
        ["recovery_soft_down quality_tryout not_eligible ADA-USD"]
    ) == "not on tryout list"
    assert short_gate_label(
        ["recovery_soft_down quality_tryout max_new_seats_per_day 1>=1"]
    ) == "tryout seat used today"
    assert short_gate_label(["sentiment 0.12 < min 0.35"]) == "sent below floor"
    assert short_gate_label(["rsi 67.8 > max_buy 55.0"]) == "RSI too high"
    assert short_gate_label(["buy_block_pairs UNI-USD"]) == "hard block list"
    assert short_gate_label(["entry_ok quality_tryout"]) is None
    assert short_gate_label(
        ["sentiment 0.015 < min 0.25", "rsi 69.8 > max_buy 55.0"],
        block_max=True,
        add_block_reason="ok",
    ) == "sent below floor"
    assert short_gate_label([], block_max=True, add_block_reason="ok") == "add-risk max"
    assert short_gate_label([], block_max=True, add_block_reason="gap_below_min") == "gap below min"
    print("PASS short_gate_label")


def test_recovery_summary_shape():
    s = recovery_policy_dashboard_summary()
    assert isinstance(s, dict)
    for k in ("active", "mode", "tryout_pairs", "label"):
        assert k in s
    if s.get("active") and str(s.get("mode") or "").startswith("quality_tryout"):
        assert isinstance(s.get("tryout_pairs"), list)
        assert s.get("label")
        assert "tryout" in str(s.get("label")).lower()
    print("PASS recovery_summary", s.get("label"), "active=", s.get("active"))


if __name__ == "__main__":
    test_short_gate_label_maps()
    test_recovery_summary_shape()
    print("OK")
