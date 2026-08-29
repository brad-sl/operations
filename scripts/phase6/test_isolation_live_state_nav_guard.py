#!/usr/bin/env python3
"""Isolation: cash-API-zero must not poison live NAV or period end total.

Repro class 2026-08-28: total $84.12 = PAXG qty×arm_vwap, cash wiped → −96% tiles.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.live_state_nav_guard import (
    guard_live_nav,
    sanitize_current_total_for_kpis,
)


def test_guard_blocks_paxg_only_cliff():
    # Prior healthy cash-heavy book
    prior_total, prior_cash = 2302.53, 2162.69
    # Bad refresh: cash API 0, only PAXG at arm_vwap
    raw_total, raw_cash, raw_hold = 84.12, 0.0, 84.12
    total, cash, hold, meta = guard_live_nav(
        new_total=raw_total,
        new_cash=raw_cash,
        new_holdings=raw_hold,
        prior_total=prior_total,
        prior_cash=prior_cash,
    )
    print("guard meta", meta, "→", total, cash, hold)
    assert meta["guarded"] is True
    assert cash >= 2000
    assert total >= 2000
    assert total > raw_total * 5
    print("PASS: PAXG-only cliff blocked")


def test_guard_allows_real_small_mtm():
    total, cash, hold, meta = guard_live_nav(
        new_total=2290.0,
        new_cash=2150.0,
        new_holdings=140.0,
        prior_total=2302.0,
        prior_cash=2162.0,
    )
    assert meta["guarded"] is False
    assert abs(total - 2290.0) < 0.01
    print("PASS: normal mtm allowed")


def test_guard_allows_cash_deploy_into_holdings():
    # Cash went into bags
    total, cash, hold, meta = guard_live_nav(
        new_total=2300.0,
        new_cash=100.0,
        new_holdings=2200.0,
        prior_total=2300.0,
        prior_cash=2200.0,
    )
    assert meta["guarded"] is False
    assert abs(cash - 100.0) < 0.01
    print("PASS: real deploy allowed")


def test_sanitize_period_end_nav():
    safe, meta = sanitize_current_total_for_kpis(84.12, 2302.34, external_flow_usd=0.0)
    print("sanitize", safe, meta)
    assert meta["sanitized"] is True
    assert safe >= 2000
    # Real withdrawal
    safe2, meta2 = sanitize_current_total_for_kpis(
        300.0, 2300.0, external_flow_usd=-2000.0
    )
    assert meta2["sanitized"] is False
    assert abs(safe2 - 300.0) < 0.01
    print("PASS: period end NAV sanitize")


def test_live_repro_period_math():
    """Bad end NAV reproduces Brad screenshot; sanitized does not."""
    from phase6.core.dashboard_serve_helpers import compute_period_performance

    db = ROOT / "data" / "phase6.db"
    if not db.exists():
        print("SKIP: no phase6.db")
        return
    bad = compute_period_performance(84.12, db, timeout=8.0)
    good_end, _ = sanitize_current_total_for_kpis(84.12, 2302.34, external_flow_usd=0.0)
    good = compute_period_performance(good_end, db, timeout=8.0)
    print("bad today", bad.get("today"), "good today", good.get("today"))
    assert bad.get("today") is not None and bad["today"] < -50
    assert good.get("today") is not None and good["today"] > -20
    print("PASS: repro + sanitize period math")


if __name__ == "__main__":
    test_guard_blocks_paxg_only_cliff()
    test_guard_allows_real_small_mtm()
    test_guard_allows_cash_deploy_into_holdings()
    test_sanitize_period_end_nav()
    test_live_repro_period_math()
    print("ALL PASS")
