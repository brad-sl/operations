#!/usr/bin/env python3
"""ISO tests — squeeze / regime / confirm helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.squeeze_regime_breakout import (  # noqa: E402
    bb_width_series,
    candle_efficiency,
    coil_then_breadth_fire,
    compression_at,
    confirm_break,
    evaluate_bar,
    regime_allows_direction,
    ttm_squeeze_on,
    atr_series,
)


def _flat_bars(n: int = 120, px: float = 100.0, vol: float = 1000.0):
    o = [px] * n
    h = [px + 0.5] * n
    l = [px - 0.5] * n
    c = [px] * n
    v = [vol] * n
    return o, h, l, c, v


def test_efficiency():
    e1 = candle_efficiency(100, 110, 90, 109)  # body 9 / range 20 = 0.45
    e_ok = candle_efficiency(100, 110, 100, 109)  # body 9 / range 10 = 0.9
    e2 = candle_efficiency(100, 110, 90, 100.1)
    assert e_ok is not None and e_ok >= 0.55
    assert e1 is not None and e1 < 0.55
    assert e2 is not None and e2 < 0.55
    print("PASS efficiency")


def test_regime_bias():
    assert regime_allows_direction("bull", "up")
    assert not regime_allows_direction("bull", "down")
    assert not regime_allows_direction("bear", "up")
    assert regime_allows_direction("flat", "up")
    print("PASS regime bias")


def test_compression_flat_tape():
    o, h, l, c, v = _flat_bars(150)
    # tight range → should compress eventually
    widths = bb_width_series(c)
    atrs = atr_series(h, l, c)
    hit = False
    for i in range(100, 150):
        st = compression_at(h, l, c, i, widths=widths, atrs=atrs)
        if st.on:
            hit = True
            break
    assert hit, "expected compression on flat tape"
    print("PASS compression flat")


def test_confirm_vol_and_break():
    n = 80
    o = [100.0] * n
    h = [101.0] * n
    l = [99.0] * n
    c = [100.0] * n
    v = [1000.0] * n
    # last bar breaks up with volume
    h[-1] = 108.0
    c[-1] = 107.0
    o[-1] = 100.5
    l[-1] = 100.0
    v[-1] = 5000.0
    atrs = atr_series(h, l, c)
    # force atr rising-ish by expanding last ranges earlier
    for j in range(n - 10, n):
        h[j] = c[j - 1] + 2.0
        l[j] = c[j - 1] - 2.0
        c[j] = c[j - 1] + 0.5
        o[j] = c[j - 1]
    h[-1], l[-1], o[-1], c[-1], v[-1] = 120.0, 110.0, 111.0, 119.0, 8000.0
    atrs = atr_series(h, l, c)
    conf = confirm_break(
        o=o[-1], h=h[-1], l=l[-1], c=c[-1], volume=v[-1], volumes=v, atrs=atrs, i=n - 1,
        range_hi=105.0, range_lo=95.0,
    )
    assert conf.break_up
    assert conf.vol_ok
    print("PASS confirm break structure", conf.confirm_up, conf.reasons)


def test_coil_breadth():
    assert coil_then_breadth_fire(compression_recent_on=True, breadth_on=True, regime="flat")
    assert not coil_then_breadth_fire(compression_recent_on=True, breadth_on=True, regime="bear")
    assert not coil_then_breadth_fire(compression_recent_on=False, breadth_on=True, regime="bull")
    print("PASS coil breadth M2")


def test_evaluate_smoke():
    o, h, l, c, v = _flat_bars(130)
    # spike break
    i = 129
    h[i], l[i], o[i], c[i], v[i] = 110.0, 100.0, 100.2, 109.5, 9000.0
    sig = evaluate_bar(opens=o, highs=h, lows=l, closes=c, volumes=v, i=i, regime="bull")
    assert isinstance(sig.long_candidate, bool)
    print("PASS evaluate smoke", sig.long_candidate, sig.compression_recent)


if __name__ == "__main__":
    test_efficiency()
    test_regime_bias()
    test_compression_flat_tape()
    test_confirm_vol_and_break()
    test_coil_breadth()
    test_evaluate_smoke()
    print("ALL squeeze_regime_breakout ISOLATION PASSED")
