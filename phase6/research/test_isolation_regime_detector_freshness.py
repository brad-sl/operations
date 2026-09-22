#!/usr/bin/env python3
"""Isolation: regime detector live merge + threshold kwargs (RC-05 / D2).

D2 change: multi-day gap fill with a single spot is REFUSED (fail-closed).
Same-day / 1-day lag tip hygiene still allowed.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.regime_detector import _merge_live_close, detect_regime


def test_merge_refuses_when_deeply_stale():
    """10d hole must not append a fake tip (D2 anti-fossil)."""
    old = date.today() - timedelta(days=10)
    closes = [(old - timedelta(days=i), 100.0 + i) for i in range(40, 0, -1)]
    closes = sorted(closes, key=lambda x: x[0])
    closes[-1] = (old, 50000.0)

    import phase6.research.regime_detector as rd

    original_live = rd._live_btc_price
    try:
        rd._live_btc_price = lambda: 60000.0  # type: ignore
        out, meta = _merge_live_close(closes)
        assert meta.get("refused_gap_fill") is True, meta
        assert meta.get("live_appended") is False
        assert out[-1][0] == old
    finally:
        rd._live_btc_price = original_live  # type: ignore
    print("  (deep stale: refuse gap fill)")


def test_merge_appends_when_one_day_lag():
    old = date.today() - timedelta(days=1)
    closes = [(old - timedelta(days=i), 100.0 + i) for i in range(40, 0, -1)]
    closes = sorted(closes, key=lambda x: x[0])
    closes[-1] = (old, 50000.0)

    import phase6.research.regime_detector as rd

    original_live = rd._live_btc_price
    try:
        rd._live_btc_price = lambda: 60000.0  # type: ignore
        out, meta = _merge_live_close(closes)
        assert meta.get("live_appended") is True, meta
        assert out[-1][1] == 60000.0
        assert out[-1][0] == date.today()
    finally:
        rd._live_btc_price = original_live  # type: ignore
    print("  (1d lag: append tip)")


def test_detect_regime_accepts_thresholds():
    d = detect_regime(
        lookback_days=30,
        bull_return_pct=50.0,  # very high → not bull
        bear_return_pct=-50.0,
        flat_abs_pct=50.0,  # almost everything flat
        use_live_price=True,
    )
    assert d["regime"] in (
        "bull",
        "bear",
        "flat",
        "transition",
        "soft_down",
        "unknown",
    )
    assert "thresholds" in d
    assert d["thresholds"]["flat_abs_pct"] == 50.0
    assert "regime_layer" in d
    assert "fresh_ok" in d or d["regime"] == "unknown"
    print("  detect thresholds + fresh_ok field OK", d.get("regime"), d.get("data_source"))


if __name__ == "__main__":
    test_merge_refuses_when_deeply_stale()
    test_merge_appends_when_one_day_lag()
    test_detect_regime_accepts_thresholds()
    print("regime_detector freshness isolation PASS")
