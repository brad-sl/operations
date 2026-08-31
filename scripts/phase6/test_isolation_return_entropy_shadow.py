#!/usr/bin/env python3
"""Isolation tests for return_entropy_shadow (unit parts need no network)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.return_entropy_shadow import (  # noqa: E402
    EntropyConfig,
    entropy_for_closes,
    histogram_probs,
    label_entropy,
    rolling_entropy_series,
    shannon_entropy_normalized,
    shannon_entropy_raw,
    simple_returns,
    telegram_summary,
)


def test_simple_returns():
    r = simple_returns([100.0, 110.0, 99.0])
    assert abs(r[0] - 0.10) < 1e-12, r
    assert abs(r[1] - (99 / 110 - 1)) < 1e-12, r
    assert simple_returns([0.0, 1.0]) == []
    assert simple_returns([1.0]) == []


def test_entropy_degenerate_and_uniform():
    # All mass in one region → H_norm near 0
    vals = [0.01] * 50
    h_n, h_r, meta = shannon_entropy_normalized(vals, n_bins=10, lo=-0.05, hi=0.05)
    assert h_n is not None and h_n < 0.15, (h_n, meta)
    assert h_r is not None and h_r < 0.5, h_r

    # Spread across bins roughly uniform on fixed grid
    # 10 bins, one sample center of each bin on [-0.05, 0.05]
    lo, hi, k = -0.05, 0.05, 10
    width = (hi - lo) / k
    uniform = [lo + (i + 0.5) * width for i in range(k)] * 5
    h_u, h_ur, meta_u = shannon_entropy_normalized(uniform, n_bins=k, lo=lo, hi=hi)
    assert h_u is not None and h_u > 0.95, (h_u, meta_u)
    assert abs(h_ur - math.log(k, 2)) < 1e-9, h_ur


def test_raw_entropy_two_outcome():
    # fair coin: H = 1 bit
    h = shannon_entropy_raw([0.5, 0.5])
    assert abs(h - 1.0) < 1e-12, h
    h0 = shannon_entropy_raw([1.0, 0.0])
    assert abs(h0 - 0.0) < 1e-12, h0


def test_histogram_clamp():
    probs = histogram_probs([-10.0, 0.0, 10.0], n_bins=5, lo=-1.0, hi=1.0)
    assert abs(sum(probs) - 1.0) < 1e-12
    assert probs[0] > 0 and probs[-1] > 0


def test_labels():
    cfg = EntropyConfig(structure_max=0.35, noise_min=0.70)
    assert label_entropy(0.20, cfg) == "structure"
    assert label_entropy(0.50, cfg) == "mid"
    assert label_entropy(0.85, cfg) == "noise"
    assert label_entropy(None, cfg) == "insufficient"


def test_rolling_causal():
    # constant returns → low entropy after warmup (fixed edges)
    rets = [0.001] * 80
    series = rolling_entropy_series(
        rets, window=30, n_bins=10, edge_mode="fixed", fixed_lo=-0.05, fixed_hi=0.05
    )
    assert all(x is None for x in series[:29])
    assert series[29] is not None and series[29] < 0.2, series[29]


def test_fixed_edges_quiet_vs_wild():
    cfg_q = EntropyConfig(
        window=40, n_bins=10, edge_mode="fixed", fixed_lo=-0.03, fixed_hi=0.03
    )
    closes_q = [100.0]
    for _ in range(60):
        closes_q.append(closes_q[-1] * 1.0002)  # tiny drift
    pe_q = entropy_for_closes(closes_q, cfg_q)
    closes_w = [100.0]
    for i in range(60):
        closes_w.append(closes_w[-1] * (1.04 if i % 2 == 0 else 1 / 1.04))
    pe_w = entropy_for_closes(closes_w, cfg_q)
    assert pe_q.ok and pe_w.ok
    assert pe_q.h_norm is not None and pe_w.h_norm is not None
    assert float(pe_q.h_norm) < float(pe_w.h_norm)
    assert pe_q.label == "structure"


def test_entropy_for_closes_structure_vs_noise_shape():
    cfg = EntropyConfig(window=40, n_bins=10, min_returns=20)
    # Nearly flat path → concentrated small returns → structure-ish
    closes_flat = [100.0]
    for _ in range(60):
        closes_flat.append(closes_flat[-1] * 1.0001)
    pe_flat = entropy_for_closes(closes_flat, cfg)
    assert pe_flat.ok and pe_flat.h_norm is not None
    assert pe_flat.label in ("structure", "mid"), pe_flat

    # Alternating large up/down → wider dispersion → higher H
    closes_choppy = [100.0]
    for i in range(60):
        mult = 1.03 if i % 2 == 0 else (1 / 1.03)
        closes_choppy.append(closes_choppy[-1] * mult)
    pe_ch = entropy_for_closes(closes_choppy, cfg)
    assert pe_ch.ok and pe_ch.h_norm is not None
    assert pe_flat.h_norm is not None
    assert float(pe_ch.h_norm) > float(pe_flat.h_norm), (pe_ch.h_norm, pe_flat.h_norm)


def test_telegram():
    assert telegram_summary({"by_label": {"structure": 0, "noise": 0}}) == ""
    body = telegram_summary(
        {
            "by_label": {"structure": 1, "noise": 1, "mid": 2},
            "pairs": [
                {"pair": "AAA-USD", "label": "structure", "h_norm": 0.2},
                {"pair": "BBB-USD", "label": "noise", "h_norm": 0.9},
            ],
        }
    )
    assert "ENTROPY shadow" in body
    assert "AAA-USD" in body


def main() -> int:
    test_simple_returns()
    test_entropy_degenerate_and_uniform()
    test_raw_entropy_two_outcome()
    test_histogram_clamp()
    test_labels()
    test_rolling_causal()
    test_fixed_edges_quiet_vs_wild()
    test_entropy_for_closes_structure_vs_noise_shape()
    test_telegram()
    print("OK test_isolation_return_entropy_shadow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
