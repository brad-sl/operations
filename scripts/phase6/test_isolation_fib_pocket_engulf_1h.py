#!/usr/bin/env python3
"""Isolation tests for fib_pocket_engulf_1h (synthetic bars — no network)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.fib_pocket_engulf_1h import (  # noqa: E402
    Spec,
    _zone,
    run_pair,
)


def test_zone_long_gold():
    z_lo, z_hi = _zone(110.0, 100.0, "gold", "long")
    # retrace 0.618-0.650 from high: 110-6.5=103.5 .. 110-6.18=103.82
    assert 103.0 < z_lo < z_hi < 104.5, (z_lo, z_hi)


def test_run_pair_thin():
    r = run_pair("TEST-USD", [], Spec())
    assert r.get("error") == "thin_bars" or r.get("n") == 0


def _synth_uptrend(n: int = 400) -> list:
    """Gentle uptrend with one clear impulse + pullback (may or may not fire)."""
    rows = []
    t0 = 1_700_000_000
    px = 100.0
    for i in range(n):
        # slow up
        px = 100.0 + i * 0.05
        o = px
        c = px + 0.02
        h = max(o, c) + 0.1
        l = min(o, c) - 0.1
        # mid impulse bump
        if 200 <= i <= 220:
            c = px + (i - 200) * 0.4
            h = c + 0.2
            o = px
            l = o - 0.1
        if 221 <= i <= 235:
            # pullback
            c = px - (i - 221) * 0.25
            o = px
            h = o + 0.05
            l = c - 0.1
        rows.append([t0 + i * 3600, l, h, o, c, 1000.0])
    return rows


def test_run_pair_synth_no_crash():
    rows = _synth_uptrend(500)
    r = run_pair("SYN-USD", rows, Spec(name="iso", trend="none"))
    assert "n" in r
    assert r.get("edge_class")
    # fees constant positive
    if r["n"] > 0:
        assert r["mean_r_net"] <= r["mean_r_gross"] + 1e-9


def main():
    test_zone_long_gold()
    test_run_pair_thin()
    test_run_pair_synth_no_crash()
    print("PASS isolation_fib_pocket_engulf_1h")


if __name__ == "__main__":
    main()
