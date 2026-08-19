#!/usr/bin/env python3
"""Isolation: flat / equal consecutive closes must still yield RSI history.

Regression for OP-USD class failure: aggressive de-dupe of equal closes
collapsed thin pairs below the 30-bar RSI threshold and blocked rebalance
(signal_freshness_enforced → incomplete_coverage).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_refresher():
    path = ROOT / "scripts" / "refresh_rsi_prices.py"
    spec = importlib.util.spec_from_file_location("refresh_rsi_prices", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_calculate_rsi_accepts_flat_series():
    mod = _load_refresher()
    # 40 flat bars — real market can print equal 15m closes
    prices = [0.099] * 40
    rsi = mod.calculate_rsi(prices, period=14)
    assert rsi, "flat series must produce RSI values"
    assert all(0.0 <= x <= 100.0 for x in rsi)
    # pure flat → RSI tends to 100 (no losses) or stable; just require finite
    assert rsi[-1] == 100.0 or rsi[-1] >= 50.0
    print("calculate_rsi_accepts_flat_series OK", rsi[-1])


def test_calculate_rsi_mild_moves_with_repeats():
    mod = _load_refresher()
    # equal closes interleaved with small ticks (OP-like thin book)
    prices = []
    px = 0.095
    for i in range(50):
        if i % 3 == 0:
            px = round(px + 0.001, 6)
        prices.append(px)
        prices.append(px)  # duplicate consecutive close is a valid bar
    # de-dupe must NOT be applied by calculate_rsi itself
    rsi = mod.calculate_rsi(prices, period=14)
    assert len(prices) >= 30
    assert rsi, f"expected RSI from n={len(prices)} with repeats"
    assert 0.0 <= rsi[-1] <= 100.0
    print("calculate_rsi_mild_moves_with_repeats OK", "n", len(prices), "rsi", rsi[-1])


def test_merge_history_does_not_collapse_equal_closes():
    mod = _load_refresher()
    existing = [0.096, 0.096, 0.097]
    new = [0.097, 0.097, 0.098, 0.098, 0.099]
    merged = mod._merge_history(existing, new, max_len=200)
    # Must retain multiplicity — not collapse to unique prices only
    assert len(merged) >= len(new), merged
    # Short existing + longer new → prefer new window (backfill path)
    short = [0.099] * 5
    long_new = [0.09 + i * 0.0001 for i in range(40)]
    # make many equals
    long_flat = [0.099] * 40
    m2 = mod._merge_history(short, long_flat, max_len=200)
    assert len(m2) >= 30, f"backfill must keep flat bars, got n={len(m2)} {m2[:5]}..."
    print("merge_history_does_not_collapse_equal_closes OK", len(merged), len(m2))


def test_flat_window_reaches_rsi_threshold_after_merge():
    mod = _load_refresher()
    # Simulate broken prior state (n=10 after bad de-dupe)
    broken = [0.099] * 10
    fetch = [0.099] * 64  # what Coinbase returned for OP with limit=100 (unique-ish)
    hist = mod._merge_history(broken, fetch, max_len=200)
    assert len(hist) >= 30, hist
    rsi = mod.calculate_rsi(hist[-100:], period=14)
    assert rsi, "OP-class backfill must unlock RSI"
    print("flat_window_reaches_rsi_threshold_after_merge OK", len(hist), rsi[-1])


if __name__ == "__main__":
    test_calculate_rsi_accepts_flat_series()
    test_calculate_rsi_mild_moves_with_repeats()
    test_merge_history_does_not_collapse_equal_closes()
    test_flat_window_reaches_rsi_threshold_after_merge()
    print("[RSI-FLAT-CANDLES] PASSED")
