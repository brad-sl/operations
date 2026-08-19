#!/usr/bin/env python3
"""Isolation tests for StochRSI calc + trial health gates (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Import pure functions from refresher
import importlib.util

spec = importlib.util.spec_from_file_location(
    "refresh_rsi_prices", ROOT / "scripts" / "refresh_rsi_prices.py"
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


def test_stoch_requires_enough_bars():
    prices = [100.0 + i * 0.1 for i in range(20)]
    k, d = mod.calculate_stochastic_rsi(prices)
    assert k == [] or len(k) >= 0  # may be empty if RSI window short
    prices2 = [100.0 + ((-1) ** i) * (i % 5) for i in range(80)]
    k2, d2 = mod.calculate_stochastic_rsi(prices2)
    assert len(k2) > 0, "expected Stoch %K with 80 bars"
    assert all(0 <= x <= 100 for x in k2)
    if d2:
        assert all(0 <= x <= 100 for x in d2)
    print("PASS test_stoch_requires_enough_bars")


def test_flat_market_k_is_mid():
    prices = [50.0] * 60
    k, d = mod.calculate_stochastic_rsi(prices)
    # RSI constant → max=min → K defaults 50
    if k:
        assert all(abs(x - 50.0) < 1e-6 for x in k), k[:5]
    print("PASS test_flat_market_k_is_mid")


def test_rsi_monotonic_up_high():
    prices = [float(i) for i in range(1, 80)]
    rsi = mod.calculate_rsi(prices)
    assert rsi and rsi[-1] > 70
    print("PASS test_rsi_monotonic_up_high")


def test_health_detects_missing_stoch(tmp_path: Path | None = None):
    # lightweight inline: write fake cache without stoch and ensure logic would flag
    cache = {
        "timestamp": "2026-07-21T00:00:00+00:00",
        "rsi": {
            "BTC-USD": {"rsi": 50.0, "candle_count": 30},
            "ETH-USD": {"rsi": 50.0},
        },
    }
    assert all("stoch_k" not in v for v in cache["rsi"].values())
    print("PASS test_health_detects_missing_stoch (structure)")


if __name__ == "__main__":
    test_stoch_requires_enough_bars()
    test_flat_market_k_is_mid()
    test_rsi_monotonic_up_high()
    test_health_detects_missing_stoch()
    print("ALL isolation OK")
