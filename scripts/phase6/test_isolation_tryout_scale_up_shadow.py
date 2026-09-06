#!/usr/bin/env python3
"""Isolation: tryout mid-flight scale-up shadow (ride the wave). No network required."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.tryout_scale_up_shadow import (  # noqa: E402
    ScaleDecision,
    _cf_summary,
    evaluate_scale_up,
    load_cfg,
)


def _pos(pair="LINK-USD", value=75.0, entry=10.0, mark=10.25, unreal=0.025):
    return {
        "pair": pair,
        "value_usd": value,
        "entry_price": entry,
        "current_price": mark,
        "unrealized_pnl_pct": unreal,
        "sleeve": "",
    }


def test_would_scale_when_gates_clear():
    cfg = load_cfg()
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    entry_ts = (now - timedelta(hours=5)).isoformat()
    pos = _pos()
    with patch(
        "phase6.core.tryout_scale_up_shadow.infer_open_lot_entry",
        return_value={
            "entry_price": 10.0,
            "entry_ts": entry_ts,
            "entry_reason": "quality_tryout_e2e",
            "tryout_tagged_buy": True,
        },
    ), patch(
        "phase6.core.tryout_scale_up_shadow._phase_and_structure",
        return_value={"phase": 1, "phase_name": "ignition", "structure_ok": True, "error": None},
    ), patch(
        "phase6.core.tryout_scale_up_shadow._load_json",
        return_value={"lots": {}},
    ):
        d = evaluate_scale_up(pos, cfg, now=now)
    assert d.status == "would_scale", d
    assert d.step_usd == 75.0
    assert "earned_mid_flight_step" in d.reasons


def test_blocked_in_bank_zone():
    cfg = load_cfg()
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    pos = _pos(unreal=0.05, mark=10.5)  # +5% past max band
    with patch(
        "phase6.core.tryout_scale_up_shadow.infer_open_lot_entry",
        return_value={
            "entry_price": 10.0,
            "entry_ts": (now - timedelta(hours=6)).isoformat(),
            "entry_reason": "quality_tryout",
            "tryout_tagged_buy": True,
        },
    ), patch(
        "phase6.core.tryout_scale_up_shadow._phase_and_structure",
        return_value={"phase": 2, "structure_ok": True, "error": None},
    ), patch(
        "phase6.core.tryout_scale_up_shadow._load_json",
        return_value={"lots": {}},
    ):
        d = evaluate_scale_up(pos, cfg, now=now)
    assert d.status == "blocked", d
    assert any("max" in r or "bank" in r for r in d.reasons)


def test_blocked_late_phase():
    cfg = load_cfg()
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    pos = _pos()
    with patch(
        "phase6.core.tryout_scale_up_shadow.infer_open_lot_entry",
        return_value={
            "entry_price": 10.0,
            "entry_ts": (now - timedelta(hours=6)).isoformat(),
            "entry_reason": "tryout",
            "tryout_tagged_buy": True,
        },
    ), patch(
        "phase6.core.tryout_scale_up_shadow._phase_and_structure",
        return_value={"phase": 3, "phase_name": "extension", "structure_ok": True, "error": None},
    ), patch(
        "phase6.core.tryout_scale_up_shadow._load_json",
        return_value={"lots": {}},
    ):
        d = evaluate_scale_up(pos, cfg, now=now)
    assert d.status == "blocked", d
    assert any("phase=" in r for r in d.reasons)


def test_sticky_skip():
    cfg = load_cfg()
    d = evaluate_scale_up(_pos(pair="BTC-USD", value=500.0), cfg)
    assert d.status == "sticky"


def test_not_tryout_large_bag():
    cfg = load_cfg()
    now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    pos = _pos(value=400.0, unreal=0.02)
    with patch(
        "phase6.core.tryout_scale_up_shadow.infer_open_lot_entry",
        return_value={
            "entry_price": 10.0,
            "entry_ts": (now - timedelta(hours=10)).isoformat(),
            "entry_reason": "rebalance_buy",
            "tryout_tagged_buy": False,
        },
    ):
        d = evaluate_scale_up(pos, cfg, now=now)
    assert d.status in ("not_tryout", "skip"), d


def test_cf_insufficient_n():
    cfg = load_cfg()
    s = _cf_summary([], cfg)
    assert s["edge_class"] == "INSUFFICIENT_N"
    s2 = _cf_summary(
        [
            {"excess_r": 0.01, "tryout_net_r": 0.02, "scale_net_r": 0.03},
            {"excess_r": 0.01, "tryout_net_r": 0.02, "scale_net_r": 0.03},
        ],
        cfg,
    )
    assert s2["edge_class"] == "INSUFFICIENT_N"


def test_live_apply_pinned_false():
    cfg = load_cfg({"live_apply": True})
    assert cfg["live_apply"] is False


def test_scale_decision_dict():
    d = ScaleDecision("X", "would_scale", 75, 0.02, 3.0, 1, True, 75.0, ["ok"])
    assert d.to_dict()["pair"] == "X"


if __name__ == "__main__":
    test_would_scale_when_gates_clear()
    test_blocked_in_bank_zone()
    test_blocked_late_phase()
    test_sticky_skip()
    test_not_tryout_large_bag()
    test_cf_insufficient_n()
    test_live_apply_pinned_false()
    test_scale_decision_dict()
    print("ALL PASS isolation_tryout_scale_up_shadow")
