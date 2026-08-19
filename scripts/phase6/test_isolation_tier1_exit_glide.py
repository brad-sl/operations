#!/usr/bin/env python3
"""Isolation: tier1 exit glide draft is non-executing and structured."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_tier1_draft():
    from phase6.research.tier1_exit_glide import scan_and_draft_glide, format_summary, persist

    d = scan_and_draft_glide()
    assert d.get("execute") is False
    assert d.get("auto_apply") is False
    assert d.get("schema") == "tier1_exit_glide_draft_v1"
    assert "capital" in d and "scan" in d
    for leg in d.get("glide_legs") or []:
        assert leg.get("side") == "SELL"
        assert leg.get("execute") is False
        assert float(leg.get("sell_usd") or 0) > 0
    # refuse execute path
    from phase6.research import tier1_exit_glide as m

    rc = m.main(["--execute"])
    assert rc == 2
    text = format_summary(d)
    assert "DRAFT" in text or "execute=false" in text.lower() or "execute=false" in str(d).lower()
    path = ROOT / "data" / "state" / "tier1_exit_glide_draft_isolation.json"
    persist(d, path=path)
    print(format_summary(d))
    print("PASS tier1 draft isolation")


if __name__ == "__main__":
    test_tier1_draft()
    print("ALL TIER1 ISOLATION PASSED")
