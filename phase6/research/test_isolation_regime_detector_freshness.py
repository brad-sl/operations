#!/usr/bin/env python3
"""Isolation: regime detector live merge + threshold kwargs (RC-05).

Verifies fresher BTC close is used to avoid stale OHLCV window_end.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.regime_detector import _merge_live_close, detect_regime


def test_merge_appends_when_stale():
    """Test that stale OHLCV gets live close appended, making window_end fresh (RC-05)."""
    old = date.today() - timedelta(days=6)
    closes = [(old - timedelta(days=i), 100.0 + i) for i in range(40, 0, -1)]
    closes = sorted(closes, key=lambda x: x[0])
    # Force last bar old
    closes[-1] = (old, 50000.0)

    import phase6.research.regime_detector as rd
    original_live = rd._live_btc_price
    try:
        rd._live_btc_price = lambda: 60000.0  # type: ignore
        out, meta = _merge_live_close(closes)
        assert meta.get("live_appended") is True, "should append when stale"
        assert out[-1][1] == 60000.0
        assert out[-1][0] == date.today()
    finally:
        rd._live_btc_price = original_live  # type: ignore

    # Also test detect produces fresh window_end
    rd._live_btc_price = lambda: 60000.0  # type: ignore
    try:
        d = detect_regime(use_live_price=True)
        assert d["window_end"] == date.today().isoformat()
        assert d["live_merge"]["live_appended"] is True
        print("  (detect also uses fresh end)")
    finally:
        rd._live_btc_price = original_live  # type: ignore


def test_detect_regime_accepts_thresholds():
    d = detect_regime(
        lookback_days=30,
        bull_return_pct=50.0,  # very high → not bull
        bear_return_pct=-50.0,
        flat_abs_pct=50.0,  # almost everything flat
        use_live_price=True,
    )
    assert d["regime"] in ("bull", "bear", "flat", "transition", "unknown")
    assert "thresholds" in d
    assert d["thresholds"]["flat_abs_pct"] == 50.0
    assert "regime_layer" in d


if __name__ == "__main__":
    test_merge_appends_when_stale()
    test_detect_regime_accepts_thresholds()
    print("regime_detector freshness isolation PASS")
