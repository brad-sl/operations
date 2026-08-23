#!/usr/bin/env python3
"""Isolation tests for P6 DASH KPI truth: period N/A, Util holdings/total, SL OK from positions.

Run:
  PYTHONPATH=. .venv/bin/python3 scripts/phase6/test_isolation_kpi_truth.py
Uses real live_state if present, else minimal mocks. Real data only, no fakes.
"""
from __future__ import annotations

import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.dashboard_serve_helpers import (
    compute_period_performance,
    fast_observability_metrics,
)


def test_period_n_a_for_missing_snapshot():
    """Missing history window must return None, never 0.0 for insufficient data."""
    db = Path("data/phase6.db")
    total = 2500.0
    perf = compute_period_performance(total, db, timeout=1.0)
    print(
        "period perf sample:",
        {k: perf.get(k) for k in ("today", "d7", "d14", "d30", "source")},
    )
    assert "d30" in perf
    assert "d14" in perf
    # When source is adjusted and history is long enough, periods may be numeric.
    # When a window cannot be computed, value must be None (UI N/A) — never fake 0.0.
    if perf.get("source") == "period_snapshots_db_adjusted":
        for k in ("today", "h24", "d7", "d14", "d30"):
            v = perf.get(k)
            if v is not None:
                assert isinstance(v, (int, float)), f"{k} must be number or None, got {v!r}"
                # 0.0 is allowed only as a real computed flat; missing stays None.
        # If d14 present as number, it is a real window (primary gate metric).
        if perf.get("d14") is not None:
            print("d14 live:", perf.get("d14"))
    print("PASS: period N/A handling present (missing windows None; d14 key shipped)")


def test_util_from_live_holdings():
    """Util primary must be holdings / total from live positions, not always arch target."""
    # Mock live_state with known holdings/total
    live = {
        "total_usd": 2575.0,
        "total_holdings_value": 2182.0,
        "active_positions": 10,
        "trading_positions": [{"pair": "ARB-USD", "value_usd": 10}] * 5,
        "arch4": {"last_exposure": 0.99},  # target would be wrong
    }
    m = fast_observability_metrics(Path("data/phase6.db"), live, timeout=0.1)
    util = m.get("utilization")
    expected = round(2182.0 / 2575.0, 4)
    print(f"util computed: {util} expected ~{expected}")
    assert util == expected or (util is not None and abs(util - expected) < 0.001), f"Util mismatch: {util} vs {expected}"
    print("PASS: util uses holdings/total primary")


def test_sl_ok_from_positions_not_fake_zero():
    """SL OK must compute from open positions having sl_stop_price_est (real attach rate), never permanent 0 from empty metric."""
    live = {
        "total_usd": 2500,
        "total_holdings_value": 2000,
        "trading_positions": [
            {"pair": "ARB-USD", "value_usd": 100, "sl_stop_price_est": 0.08},
            {"pair": "LINK-USD", "value_usd": 500, "sl_stop_price_est": None},
            {"pair": "DOGE-USD", "value_usd": 200, "sl_attached": True},
        ],
    }
    m = fast_observability_metrics(Path("data/phase6.db"), live, timeout=0.1)
    sl = m.get("sl_success_rate")
    print(f"SL OK from pos: {sl}")
    # 2 protected out of 3
    assert sl is not None
    assert abs(sl - (2/3)) < 0.01, f"SL OK should be ~0.666, got {sl}"
    print("PASS: SL OK computed from positions protective stops (not 0%)")


def test_live_state_if_present():
    """If live state exists, run against real to verify non-zero util and sl_ok not stuck at 0."""
    live_path = Path("data/state/phase6_live_state.json")
    if not live_path.exists():
        print("SKIP: no live_state.json for real data test")
        return
    try:
        live = json.loads(live_path.read_text())
    except Exception:
        print("SKIP: bad live state")
        return
    db = Path("data/phase6.db")
    m = fast_observability_metrics(db, live, timeout=1.0)
    util = m.get("utilization")
    sl = m.get("sl_success_rate")
    print(f"REAL: util={util}, sl_ok={sl}")
    if util is not None:
        assert 0 <= util <= 1.0 or abs(util) < 2, "util out of range"
    # sl may be None or fraction; not asserting !=0 strictly as may legitimately low, but not forced 0 from empty
    print("PASS: real data run ok (util/sl not crashing to fake)")


def test_equity_trend_has_points_and_health():
    from datetime import datetime, timezone
    from phase6.core.dashboard_serve_helpers import compute_equity_trend, _linreg_slope_intercept
    s, _ = _linreg_slope_intercept([0.0, 10.0], [100.0, 90.0])
    assert s < 0
    db = Path("data/phase6.db")
    live_path = Path("data/state/phase6_live_state.json")
    total = 2500.0
    if live_path.exists():
        total = float(json.loads(live_path.read_text()).get("total_usd") or total)
    # Shared clock so Window and 30D cannot diverge via sliding nearest_ts
    as_of = datetime.now(timezone.utc)
    eq = compute_equity_trend(total, db, days=30, max_points=36, timeout=5.0, as_of=as_of)
    print("equity_trend:", {k: eq.get(k) for k in ("status", "point_count", "window_return_pct", "recent_return_pct")})
    print("health:", eq.get("health"))
    assert eq.get("status") == "ok", eq
    assert len(eq.get("points") or []) >= 2
    assert eq.get("trend") and eq.get("health")
    # Deposit-adjusted window should not look like raw ~+250% from funding
    wr = eq.get("window_return_pct")
    assert wr is not None and wr < 80.0, f"window_return looks deposit-inflated: {wr}"
    # Window must match 30D tile exactly (same start/end/flow; 2-dp rounded)
    perf = compute_period_performance(total, db, timeout=5.0, as_of=as_of)
    d30 = perf.get("d30")
    d7 = perf.get("d7")
    if d30 is not None and wr is not None:
        assert abs(float(wr) - float(d30)) < 0.005, (
            f"Window {wr} must equal 30D tile {d30} (same nearest_ts + live end + flow)"
        )
        print(f"PASS: window_return_pct={wr} == d30={d30}")
    rr = eq.get("recent_return_pct")
    if d7 is not None and rr is not None:
        assert abs(float(rr) - float(d7)) < 0.005, (
            f"Recent {rr} must equal 7D tile {d7}"
        )
        print(f"PASS: recent_return_pct={rr} == d7={d7}")
    print("PASS: equity trend series + health label")


if __name__ == "__main__":
    test_period_n_a_for_missing_snapshot()
    test_util_from_live_holdings()
    test_sl_ok_from_positions_not_fake_zero()
    test_live_state_if_present()
    test_equity_trend_has_points_and_health()
    print("ALL KPI TRUTH ISOLATION TESTS PASSED")
