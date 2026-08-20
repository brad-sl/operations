#!/usr/bin/env python3
"""Isolation: regime boundary layers + shadow gate purity (no live side effects)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.regime_detector import classify_regime_layer
from phase6.research.run_regime_boundary_layer_shadow import evaluate_shadow_gates


def test_classify_layers_default_cuts():
    # bull / bear / flat
    assert classify_regime_layer(16)["regime_layer"] == "bull"
    assert classify_regime_layer(16)["regime"] == "bull"
    assert classify_regime_layer(-12)["regime_layer"] == "bear"
    assert classify_regime_layer(3)["regime_layer"] == "flat"
    assert classify_regime_layer(-3)["regime_layer"] == "flat"
    # residual
    assert classify_regime_layer(-9)["regime_layer"] == "soft_down"
    assert classify_regime_layer(-9)["regime"] == "transition"
    assert classify_regime_layer(9.0)["regime_layer"] == "soft_up"  # 8..10
    assert classify_regime_layer(11.0)["regime_layer"] == "climb"  # 10..14
    assert classify_regime_layer(14.2)["regime_layer"] == "pre_bull"  # 14..15
    assert classify_regime_layer(9)["shadow_stance"] == "flat_b_tight"
    assert classify_regime_layer(11)["shadow_stance"] == "micro_climb"
    assert classify_regime_layer(14.5)["shadow_stance"] == "micro_pre_bull"


def test_shadow_gates_cream_not_chase():
    # climb + overbought RSI → no
    r = evaluate_shadow_gates(
        layer="climb",
        pair="LINK-USD",
        rsi=63.0,
        sentiment=0.35,
        is_new_pair=False,
        blocked=False,
        util=0.14,
    )
    assert r["would_buy"] is False
    assert any("rsi" in x for x in r["reasons"])

    # climb + good RSI/sent → yes
    r2 = evaluate_shadow_gates(
        layer="climb",
        pair="ETH-USD",
        rsi=48.0,
        sentiment=0.35,
        is_new_pair=False,
        blocked=False,
        util=0.14,
    )
    assert r2["would_buy"] is True

    # park layer never
    r3 = evaluate_shadow_gates(
        layer="soft_down",
        pair="ETH-USD",
        rsi=40.0,
        sentiment=0.5,
        is_new_pair=True,
        blocked=False,
        util=0.1,
    )
    assert r3["would_buy"] is False


def test_detect_regime_emits_layer():
    from phase6.research.regime_detector import detect_regime

    d = detect_regime(use_live_price=True)
    assert "regime_layer" in d
    assert d["regime"] in ("bull", "bear", "flat", "transition", "unknown")
    assert d["regime_layer"]


if __name__ == "__main__":
    test_classify_layers_default_cuts()
    test_shadow_gates_cream_not_chase()
    test_detect_regime_emits_layer()
    print("regime_boundary_layers isolation PASS")
