#!/usr/bin/env python3
"""Isolation tests for pair discovery funnel (mocked HTTP — no live network)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.pair_discovery import (  # noqa: E402
    DiscoveryConfig,
    PrequalRow,
    ProductRow,
    QualityRow,
    build_contenders,
    stage1_prequal,
    stage2_quality,
)


def test_build_contenders_excludes_active_and_requires_pass():
    active = ["BTC-USD", "ETH-USD"]
    prequal = [
        PrequalRow("HOT-USD", 10, 8, 11, 7, 1e6, 9e6, 0.25, 0.4, energy=0.9),
        PrequalRow("BTC-USD", 60_000, 59_000, 61_000, 58_000, 100, 6e9, 0.02, 0.05, energy=0.8),
        PrequalRow("MEH-USD", 1, 1, 1.01, 0.99, 1e5, 1e5, 0.0, 0.02, energy=0.3),
    ]
    quality = [
        QualityRow("HOT-USD", 0.9, 0.12, 0.2, 1.5, 2.0, 0.7, 100, 10.0, True, "pass"),
        QualityRow("BTC-USD", 0.8, 0.01, 0.02, 1.0, 1.0, 0.5, 100, 60000.0, True, "pass"),
        QualityRow("MEH-USD", 0.3, 0.0, 0.0, 0.9, 0.9, 0.2, 100, 1.0, False, "below"),
    ]
    cfg = DiscoveryConfig(contender_top_n=5, exclude_active_from_contenders=True)
    c = build_contenders(quality, prequal, active, cfg)
    ids = [x.product_id for x in c]
    assert "HOT-USD" in ids
    assert "BTC-USD" not in ids
    assert "MEH-USD" not in ids
    assert c[0].promote_eligible is True
    print("PASS test_build_contenders_excludes_active_and_requires_pass")


def test_stage1_filters_min_volume_and_ranks_energy():
    universe = [
        ProductRow("A-USD", "A", "USD", "online", 1.0, False),
        ProductRow("B-USD", "B", "USD", "online", 1.0, False),
        ProductRow("C-USD", "C", "USD", "online", 1.0, False),
    ]

    def fake_stats(pid, timeout):
        # A: high vol + strong up day
        # B: high vol flat
        # C: tiny volume (filtered)
        table = {
            "A-USD": {
                "open": "10",
                "high": "13",
                "low": "10",
                "last": "12.5",
                "volume": "1000000",
            },
            "B-USD": {
                "open": "10",
                "high": "10.2",
                "low": "9.9",
                "last": "10.05",
                "volume": "1000000",
            },
            "C-USD": {
                "open": "10",
                "high": "15",
                "low": "10",
                "last": "14",
                "volume": "10",
            },
        }
        return table[pid]

    cfg = DiscoveryConfig(min_quote_volume_24h_usd=1_000_000.0, prequal_top_n=10, max_stats_workers=2)
    with patch("phase6.core.pair_discovery._fetch_stats", side_effect=fake_stats):
        rows = stage1_prequal(universe, cfg)
    ids = [r.product_id for r in rows]
    assert "C-USD" not in ids
    assert "A-USD" in ids and "B-USD" in ids
    # A should rank above B (upside + range)
    assert rows[0].product_id == "A-USD"
    print("PASS test_stage1_filters_min_volume_and_ranks_energy")


def test_stage2_quality_uses_candles():
    prequal = [
        PrequalRow("Z-USD", 20, 10, 21, 9, 1e6, 2e7, 1.0, 1.2, energy=0.95),
    ]
    # Build synthetic rising candles: [t, low, high, open, close, vol]
    candles = []
    price = 10.0
    for i in range(100):
        price *= 1.01
        candles.append([i, price * 0.99, price * 1.01, price * 0.995, price, 1000 + i * 10])
    # API returns newest first — our fetcher reverses; mock already oldest-first path via _fetch_candles

    def fake_candles(pid, gran, limit, timeout=15.0):
        return candles[-limit:]

    cfg = DiscoveryConfig(min_candles=48, min_quality_score=0.0)
    with patch("phase6.core.pair_discovery._fetch_candles", side_effect=fake_candles):
        q = stage2_quality(prequal, cfg)
    assert len(q) == 1
    assert q[0].mom_3d > 0
    assert q[0].n_candles >= 48
    print("PASS test_stage2_quality_uses_candles")


if __name__ == "__main__":
    test_build_contenders_excludes_active_and_requires_pass()
    test_stage1_filters_min_volume_and_ranks_energy()
    test_stage2_quality_uses_candles()
    print("ALL pair discovery isolation tests PASS")
