#!/usr/bin/env python3
"""Isolation: goldilocks swap-rank shadow (no network required for unit path)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.goldilocks_swap_shadow import (
    GoldilocksScore,
    _base_energy_score,
    _advantage_claim,
    score_pair_goldilocks,
)


def _synth_coil_then_break(n: int = 80) -> list:
    """Flat coil then upside break with volume."""
    rows = []
    px = 100.0
    for i in range(n):
        if i < n - 5:
            # tight range
            o = px
            c = px + (0.05 if i % 2 == 0 else -0.05)
            h = max(o, c) + 0.15
            l = min(o, c) - 0.15
            v = 1000.0
            px = c
        elif i == n - 5:
            o, c = px, px + 0.1
            h, l, v = c + 0.2, o - 0.1, 1100.0
            px = c
        else:
            # expansion break
            o = px
            c = px * 1.03
            h = c * 1.01
            l = o * 0.99
            v = 3500.0
            px = c
        rows.append({"t": float(1_700_000_000 + i * 86400), "o": o, "h": h, "l": l, "c": c, "v": v})
    return rows


def _synth_extended_run(n: int = 80) -> list:
    rows = []
    px = 50.0
    for i in range(n):
        o = px
        c = px * 1.02
        h = c * 1.005
        l = o * 0.998
        v = 2000.0
        px = c
        rows.append({"t": float(1_700_000_000 + i * 86400), "o": o, "h": h, "l": l, "c": c, "v": v})
    return rows


def test_score_runs():
    g = score_pair_goldilocks("TEST-USD", candles=_synth_coil_then_break(), regime="bull")
    assert g.ok_data, g
    assert 0.0 <= g.urgency <= 1.0, g
    # extended should get late penalty path often
    g2 = score_pair_goldilocks("RUN-USD", candles=_synth_extended_run(), regime="bull")
    assert g2.ok_data, g2
    print("PASS score_runs", "coil_u", round(g.urgency, 3), "ext_u", round(g2.urgency, 3), "late", g2.structure_late)


def test_base_energy():
    s = _base_energy_score("X", _synth_extended_run())
    assert 0 <= s <= 1
    print("PASS base_energy", round(s, 3))


def test_advantage_claim_sparse():
    stats = {
        "goldilocks": {"7": [0.01, 0.02]},
        "baseline": {"7": [0.0]},
        "when_differs": {"7": []},
    }
    c = _advantage_claim(stats)
    assert "sparse" in c or "inconclusive" in c, c
    print("PASS advantage_sparse", c)


def test_boost_math():
    base, urg, scale = 0.40, 0.80, 0.35
    boosted = min(1.0, base + scale * urg)
    assert abs(boosted - 0.68) < 1e-9
    # primed inject can flip rank vs pure energy
    a_base, b_base = 0.55, 0.50
    a_u, b_u = 0.10, 0.90
    a_b = a_base + scale * a_u
    b_b = b_base + scale * b_u
    assert b_b > a_b  # goldilocks flips B above A
    print("PASS boost_math flip")


def main():
    test_score_runs()
    test_base_energy()
    test_advantage_claim_sparse()
    test_boost_math()
    print("ALL PASS isolation_goldilocks_swap_shadow")


if __name__ == "__main__":
    main()
