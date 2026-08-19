#!/usr/bin/env python3
"""Deposit must not inflate period return % (isolation)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.dashboard_serve_helpers import compute_period_performance
from phase6.core.portfolio_external_flows import classify_external_flow_usd


def test_classify_deposit():
    # $1000 cash in, holdings flat
    f = classify_external_flow_usd(1000.0, 1000.0, 0.0)
    assert abs(f - 1000.0) < 0.01, f


def test_classify_rebalance_not_deposit():
    # cash to holdings internal move
    f = classify_external_flow_usd(0.0, -500.0, 500.0)
    assert abs(f) < 0.01, f


def test_live_db_today_not_deposit_inflated():
    live = Path("data/state/phase6_live_state.json")
    if not live.exists():
        print("SKIP no live state")
        return
    import json

    st = json.loads(live.read_text())
    total = float(st.get("total_usd") or 0)
    if total < 1000:
        print("SKIP small total — no recent deposit scenario")
        return
    db = Path("data/phase6.db")
    perf = compute_period_performance(total, db, timeout=3.0)
    raw_would_be = 146.0  # known bad case from user report
    assert perf.get("h24", 0) < 20.0, perf
    assert perf.get("today", 0) < 20.0, perf
    assert perf.get("external_flows_usd", {}).get("h24", 0) >= 500, perf
    print("PASS deposit-adjusted performance", perf)


if __name__ == "__main__":
    test_classify_deposit()
    test_classify_rebalance_not_deposit()
    test_live_db_today_not_deposit_inflated()
    print("ALL PASS")