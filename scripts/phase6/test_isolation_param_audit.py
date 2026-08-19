#!/usr/bin/env python3
"""Isolation tests for P6 param audit (no live API)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.param_audit import (
    ParamSnapshot,
    audit_verified_fill,
    _confidence_score,
)


def test_stop_within_sl_max():
    params = ParamSnapshot(sl_max_pct=0.05, sl_min_pct=0.015, basket=["SOL-USD"])
    row = {
        "order_id": "abc",
        "pair": "SOL-USD",
        "side": "SELL",
        "reason": "stop_loss_exchange",
        "fill_verified": True,
        "timestamp": "2026-07-08T04:01:00Z",
        "entry_price": 80.0,
        "exit_price": 77.6,
        "pnl_pct": -0.03,
    }
    findings = audit_verified_fill(row, params, registry={}, decisions=[])
    statuses = {f.rule: f.status for f in findings}
    assert statuses.get("sl_inferred") == "pass", findings


def test_stop_exceeds_sl_max_fails():
    params = ParamSnapshot(sl_max_pct=0.05, basket=["SOL-USD"])
    row = {
        "order_id": "abc2",
        "pair": "SOL-USD",
        "side": "SELL",
        "reason": "stop_loss_exchange",
        "fill_verified": True,
        "timestamp": "2026-07-08T04:01:00Z",
        "entry_price": 100.0,
        "exit_price": 90.0,
    }
    findings = audit_verified_fill(row, params, registry={}, decisions=[])
    assert any(f.status == "fail" for f in findings)


def test_buy_pass():
    params = ParamSnapshot(basket=["LINK-USD"])
    row = {
        "order_id": "buy1",
        "pair": "LINK-USD",
        "side": "BUY",
        "reason": "rebalance_buy",
        "fill_verified": True,
        "timestamp": "2026-07-07T12:00:00Z",
    }
    findings = audit_verified_fill(row, params, registry={}, decisions=[])
    assert any(f.status == "pass" for f in findings)


def test_confidence_score():
    assert _confidence_score({"pass": 10, "warn": 2, "fail": 0}, 10) > 0.5
    assert _confidence_score({"pass": 0, "warn": 0, "fail": 5}, 5) < 0.5


if __name__ == "__main__":
    test_stop_within_sl_max()
    test_stop_exceeds_sl_max_fails()
    test_buy_pass()
    test_confidence_score()
    print("test_isolation_param_audit: PASS")