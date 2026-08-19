#!/usr/bin/env python3
"""Isolation tests for kelly_sizing (no network, no live config writes)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.kelly_sizing import (
    apply_trade_to_equity,
    clamp_to_envelopes,
    estimate_edge_from_returns,
    fractional_kelly,
    kelly_fraction,
    map_risk_fraction_to_deploy_pct,
    risk_budget_to_notional,
)


def test_article_55_2to1():
    """Classic: p=0.55, b=2 → full ≈ 0.325, half ≈ 0.1625."""
    f = kelly_fraction(0.55, 2.0)
    assert abs(f - 0.325) < 1e-9, f
    h = fractional_kelly(0.55, 2.0, 0.5)
    assert abs(h - 0.1625) < 1e-9, h
    q = fractional_kelly(0.55, 2.0, 0.25)
    assert abs(q - 0.08125) < 1e-9, q
    print("PASS test_article_55_2to1", f, h, q)


def test_zero_and_negative_edge():
    assert kelly_fraction(0.5, 1.0) == 0.0  # even money, no edge
    assert kelly_fraction(0.4, 1.0) == 0.0  # negative edge
    assert kelly_fraction(0.0, 2.0) == 0.0
    assert kelly_fraction(0.6, 0.0) == 0.0
    assert kelly_fraction(-0.1, 2.0) == 0.0
    assert fractional_kelly(0.4, 1.2, 0.5) == 0.0  # clearly negative edge
    print("PASS test_zero_and_negative_edge")


def test_bad_p_overestimate_inflates_f():
    """Wrong high p → much larger f (estimation trap)."""
    true_f = kelly_fraction(0.55, 2.0)
    bad_f = kelly_fraction(0.70, 2.0)
    assert bad_f > true_f
    assert bad_f > 0.5  # dangerously large
    print("PASS test_bad_p_overestimate_inflates_f", true_f, bad_f)


def test_risk_budget_to_notional():
    # f=0.05, equity=1000, sl=3% → position = 0.05*1000/0.03 ≈ 1666.67
    pos = risk_budget_to_notional(0.05, 1000.0, 0.03)
    assert abs(pos - (0.05 * 1000 / 0.03)) < 1e-9
    assert risk_budget_to_notional(0, 1000, 0.03) == 0.0
    assert risk_budget_to_notional(0.05, 1000, 0) == 0.0
    print("PASS test_risk_budget_to_notional", pos)


def test_clamps_never_exceed_envelopes():
    equity = 1000.0
    raw = risk_budget_to_notional(0.25, equity, 0.03)  # huge ~8333
    r = clamp_to_envelopes(
        raw,
        equity=equity,
        f_requested=0.25,
        deploy_pct=0.72,
        regime_target_max_util_pct=0.65,
        min_reserve_usd=50.0,
        max_position_usd=400.0,
        rebalance_cap_usd=200.0,
        cash_usd=1000.0,
        already_deployed_usd=0.0,
    )
    assert r.position_usd <= 200.0 + 1e-9  # rebalance cap tightest among 200/400/720/650/950
    assert r.position_usd <= 400.0
    assert r.position_usd <= equity * 0.72
    assert r.position_usd <= equity * 0.65
    assert r.position_usd <= equity - 50.0
    assert r.binding_constraint in {
        "rebalance_cap_usd",
        "max_position_usd",
        "deploy_pct_budget",
        "regime_util_budget",
        "reserve_cash_room",
    }
    print("PASS test_clamps_never_exceed_envelopes", r.position_usd, r.binding_constraint)

    # reserve binds when cash tight
    r2 = clamp_to_envelopes(
        500.0,
        equity=200.0,
        f_requested=0.1,
        deploy_pct=0.95,
        regime_target_max_util_pct=0.95,
        min_reserve_usd=80.0,
        cash_usd=100.0,
        already_deployed_usd=100.0,
    )
    assert r2.position_usd <= 20.0 + 1e-9  # cash 100 - reserve 80
    print("PASS test_reserve_binds", r2.position_usd, r2.binding_constraint)


def test_map_deploy_and_path_step():
    dep = map_risk_fraction_to_deploy_pct(0.05, 0.03, haircut=0.5)
    # 0.5 * 0.05/0.03 ≈ 0.833
    assert abs(dep - (0.5 * 0.05 / 0.03)) < 1e-9
    step = apply_trade_to_equity(
        1000.0,
        trade_return=-0.03,
        f_risk=0.02,
        sl_pct=0.03,
        envelopes={"deploy_pct": 0.9, "regime_target_max_util_pct": 0.9, "min_reserve_usd": 0},
    )
    # position = 0.02*1000/0.03 ≈ 666.67, pnl ≈ -20
    assert abs(step["pnl"] - (-20.0)) < 0.01
    print("PASS test_map_deploy_and_path_step", dep, step["pnl"])


def test_estimate_edge_helpers():
    e = estimate_edge_from_returns([0.1, 0.1, -0.05, -0.05])
    assert e["n"] == 4
    assert abs(e["p"] - 0.5) < 1e-9
    assert abs(e["b"] - 2.0) < 1e-6
    assert e["insufficient"] is False
    empty = estimate_edge_from_returns([])
    assert empty["insufficient"] is True
    print("PASS test_estimate_edge_helpers", e["f_full"])


if __name__ == "__main__":
    test_article_55_2to1()
    test_zero_and_negative_edge()
    test_bad_p_overestimate_inflates_f()
    test_risk_budget_to_notional()
    test_clamps_never_exceed_envelopes()
    test_map_deploy_and_path_step()
    test_estimate_edge_helpers()
    print("ALL isolation OK")
