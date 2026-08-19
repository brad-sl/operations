#!/usr/bin/env python3
"""Diagnose 1D/7D/14D/30D tiles vs Account Health window_return mismatch."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase6.core.dashboard_serve_helpers import (
    _nearest_ts,
    _parse_ts,
    _total_usd_at_ts,
    compute_equity_trend,
    compute_period_performance,
)
from phase6.core.portfolio_external_flows import (
    adjusted_period_return_pct,
    net_external_flow_between,
)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ls = json.loads((root / "data/state/phase6_live_state.json").read_text())
    total = float(ls.get("total_usd") or ls.get("total_balance") or 0)
    print("live_total", total)
    db = root / "data/phase6.db"

    t0 = time.time()
    perf = compute_period_performance(total, db, timeout=8.0)
    print("period_s", round(time.time() - t0, 2), {k: perf.get(k) for k in ("today", "h24", "d7", "d14", "d30", "source")})
    print("flows", perf.get("external_flows_usd"))

    t0 = time.time()
    eq = compute_equity_trend(total, db, days=30, max_points=48, timeout=12.0)
    print("equity_s", round(time.time() - t0, 2))
    print(
        {
            k: eq.get(k)
            for k in (
                "status",
                "days",
                "window_return_pct",
                "recent_return_pct",
                "point_count",
                "error",
            )
        }
    )
    if eq.get("points"):
        print("first", eq["points"][0])
        print("last", eq["points"][-1])
    if eq.get("trend"):
        print("trend", eq["trend"])

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=8)
    now = datetime.now(timezone.utc)
    end_ts = conn.execute("SELECT MAX(ts) FROM account_balances").fetchone()[0]
    end_nav = _total_usd_at_ts(conn, end_ts) if end_ts else None
    for days in (1, 7, 14, 30):
        ts = _nearest_ts(conn, now - timedelta(days=days))
        past = _total_usd_at_ts(conn, ts) if ts else None
        flow = (
            net_external_flow_between(conn, ts, end_ts, _total_usd_at_ts)
            if ts and end_ts
            else None
        )
        print(
            f"endpoint_d{days}",
            {
                "ts": ts,
                "past": round(past, 2) if past else None,
                "end_nav": round(end_nav, 2) if end_nav else None,
                "flow": flow,
                "r_vs_live": adjusted_period_return_pct(total, past, flow) if past else None,
                "r_vs_endnav": adjusted_period_return_pct(end_nav, past, flow)
                if past and end_nav
                else None,
            },
        )

    if eq.get("points") and len(eq["points"]) >= 2:
        a = _parse_ts(eq["points"][0]["t"])
        b = _parse_ts(eq["points"][-1]["t"])
        if a and b:
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            print("chart_span_days", round((b - a).total_seconds() / 86400, 3))
        t_a = eq["points"][0]["t"]
        nav_a = eq["points"][0]["nav_usd"]
        nav_b = eq["points"][-1]["nav_usd"]
        # Use end_ts for flow end when last sample is synthetic "now"
        t_b_flow = end_ts or eq["points"][-1]["t"]
        flow_ab = net_external_flow_between(conn, t_a, t_b_flow, _total_usd_at_ts)
        print(
            "chart_single_hop",
            {
                "nav_a": nav_a,
                "nav_b": nav_b,
                "flow_ab": flow_ab,
                "r": adjusted_period_return_pct(nav_b, nav_a, flow_ab),
                "index_window": eq.get("window_return_pct"),
            },
        )
    conn.close()


if __name__ == "__main__":
    main()
