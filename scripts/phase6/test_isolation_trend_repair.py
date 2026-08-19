#!/usr/bin/env python3
"""Isolation: trend_repair status builds and stays non-promoting."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_trend_repair_status():
    from phase6.research.trend_repair import (
        build_trend_repair_status,
        format_brief_lines,
        persist_status,
        PLAYBOOK,
    )

    st = build_trend_repair_status(days=30, max_points=36, timeout=6.0)
    assert st.get("schema") == "trend_repair_status_v1"
    assert st.get("auto_promote") is False
    assert st.get("playbook") == PLAYBOOK
    assert st.get("diagnosis", {}).get("primary_layer")
    assert isinstance(st.get("recommendations"), list) and len(st["recommendations"]) >= 2
    for r in st["recommendations"]:
        assert r.get("auto_apply") is False
        assert "tier" in r
    eq = st.get("equity_trend") or {}
    assert eq.get("status") in ("ok", "insufficient_history", "no_data") or str(eq.get("status", "")).startswith(
        "error"
    )
    if eq.get("status") == "ok":
        wr = eq.get("window_return_pct")
        # deposit-adjusted window should not look like raw +250% funding jump
        if wr is not None:
            assert wr < 80.0, wr
    text, frag = format_brief_lines(st)
    assert "TREND-REPAIR" in text
    assert "trend_repair" in frag
    path = ROOT / "data" / "state" / "trend_repair_status_isolation.json"
    persist_status(st, path=path)
    assert path.exists()
    print("PASS:", st.get("operator_summary"))
    print("layer:", st["diagnosis"]["primary_layer"])
    print("recs:", [r["action"] for r in st["recommendations"]])


if __name__ == "__main__":
    test_trend_repair_status()
    print("ALL TREND REPAIR ISOLATION TESTS PASSED")
