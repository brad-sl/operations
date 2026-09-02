#!/usr/bin/env python3
"""Isolation: buy_block_pairs + recovery_soft_down gate on evaluate_buy_entry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import (  # noqa: E402
    collect_buy_block_pairs,
    evaluate_buy_entry,
    load_policy,
    resolve_regime_cash,
)


def _bull_snap(pol: dict):
    pol = json.loads(json.dumps(pol))
    pol.setdefault("regimes", {}).setdefault("bull", {})
    pol["regimes"]["bull"]["strategy_mode"] = "deploy"
    pol["regimes"]["bull"]["allow_new_buys"] = True
    pol["regimes"]["bull"]["entry"] = {
        "min_sentiment": -1.0,
        "min_sentiment_new_pair": -1.0,
        "max_rsi": 100.0,
        "require_lockout_clear": True,
    }
    return resolve_regime_cash(
        policy=pol,
        detection={"regime": "bull", "confidence": 1.0, "btc_return_pct": 20.0},
    )


def test_collect_live_config_includes_uni_rave():
    pol = load_policy()
    blocks = collect_buy_block_pairs(pol)
    assert "UNI-USD" in blocks, blocks
    assert "RAVE-USD" in blocks, blocks


def test_evaluate_blocks_uni_even_bull_good_signals():
    pol = load_policy()
    snap = _bull_snap(pol)
    dec = evaluate_buy_entry(
        "UNI-USD",
        snap,
        sentiment=0.9,
        rsi=40.0,
        is_new_pair=True,
        policy=pol,
    )
    assert dec.allowed is False, dec.reasons
    assert any("block" in r.lower() or "UNI" in r for r in dec.reasons), dec.reasons


def test_evaluate_blocks_rave():
    pol = load_policy()
    snap = _bull_snap(pol)
    dec = evaluate_buy_entry(
        "RAVE-USD",
        snap,
        sentiment=0.9,
        rsi=40.0,
        is_new_pair=True,
        policy=pol,
    )
    assert dec.allowed is False, dec.reasons


def test_btc_not_on_explicit_block_list():
    """BTC may still pass sentiment/rsi; must not hit buy_block_pairs reason."""
    pol = load_policy()
    snap = _bull_snap(pol)
    dec = evaluate_buy_entry(
        "BTC-USD",
        snap,
        sentiment=0.9,
        rsi=40.0,
        is_new_pair=False,
        policy=pol,
    )
    assert not any("buy_block_pairs" in r for r in dec.reasons), dec.reasons
    # held BTC add path should be allowed under bull good signals
    assert dec.allowed is True, dec.reasons


def test_recovery_allowlist_blocks_new_alt_when_soft_down_snap():
    pol = load_policy()
    pol = json.loads(json.dumps(pol))
    pol["buy_block_pairs"] = []
    oo = pol.setdefault("operator_override", {})
    rec = oo.setdefault("recovery_soft_down_20260828", {})
    rec["enabled"] = True
    rec["block_new_buy_pairs"] = []
    rec["new_alt_policy"] = "block_unless_allowlist"
    rec["allowlist_pairs"] = ["BTC-USD", "PAXG-USD"]
    # drop quality_tryout if present so legacy path is pure
    rec.pop("quality_tryout", None)
    from phase6.core import regime_cash_policy as rcp
    from phase6.core.regime_cash_policy import RegimeCashSnapshot

    snap = RegimeCashSnapshot(
        regime="soft_down",
        confidence=1.0,
        btc_return_pct=-5.0,
        strategy_mode="deploy",
        allow_new_buys=True,
        target_max_util_pct=0.4,
        rebalance_cap_usd=40.0,
        min_cash_reserve_pct=0.1,
        entry={},
        exit={},
        label="soft_down",
        detector={},
        regime_layer="soft_down",
    )
    reason = rcp.recovery_soft_down_blocks_pair(
        "SOL-USD", policy=pol, is_new_pair=True, snap=snap
    )
    assert reason and "allowlist" in reason, reason


def _soft_snap(**kw):
    from phase6.core.regime_cash_policy import RegimeCashSnapshot

    base = dict(
        regime="bull",
        confidence=1.0,
        btc_return_pct=20.0,
        strategy_mode="deploy",
        allow_new_buys=True,
        target_max_util_pct=0.85,
        rebalance_cap_usd=100.0,
        min_cash_reserve_pct=0.1,
        entry={
            "min_sentiment": -0.1,
            "min_sentiment_new_pair": 0.25,
            "max_rsi": 70.0,
            "require_lockout_clear": True,
        },
        exit={},
        label="bull",
        detector={},
        regime_layer="bull",
    )
    base.update(kw)
    return RegimeCashSnapshot(**base)


def test_quality_tryout_allows_link_blocks_sol():
    """Brad GO thaw A: LINK/ETH tryout ok; SOL still not eligible."""
    pol = json.loads(json.dumps(load_policy()))
    pol["buy_block_pairs"] = []
    oo = pol.setdefault("operator_override", {})
    rec = oo.setdefault("recovery_soft_down_20260828", {})
    rec["enabled"] = True
    rec["block_new_buy_pairs"] = ["UNI-USD", "RAVE-USD"]
    rec["new_alt_policy"] = "quality_tryout"
    rec["allowlist_pairs"] = ["BTC-USD", "PAXG-USD", "USDC-USD"]
    rec["quality_tryout"] = {
        "tryout_pairs": ["ETH-USD", "LINK-USD"],
        "min_sentiment": 0.30,
        "max_rsi": 55.0,
        "max_new_seats_per_day": 99,  # isolation: don't trip day cap
        "abs_cap_usd": 75.0,
    }
    from phase6.core import regime_cash_policy as rcp

    # force health via snap layer
    snap = _soft_snap(regime_layer="soft_down", regime="soft_down")
    # membership
    assert rcp.recovery_soft_down_blocks_pair(
        "SOL-USD", policy=pol, is_new_pair=True, snap=snap
    )
    assert rcp.recovery_soft_down_blocks_pair(
        "LINK-USD", policy=pol, is_new_pair=True, snap=snap
    ) is None
    # quality floors
    bad_sent = evaluate_buy_entry(
        "LINK-USD", snap, sentiment=0.20, rsi=40.0, is_new_pair=True, policy=pol
    )
    assert bad_sent.allowed is False
    assert any("sentiment" in r for r in bad_sent.reasons), bad_sent.reasons
    good = evaluate_buy_entry(
        "LINK-USD", snap, sentiment=0.50, rsi=40.0, is_new_pair=True, policy=pol
    )
    assert good.allowed is True, good.reasons
    assert any("quality_tryout" in r for r in good.reasons), good.reasons
    sol = evaluate_buy_entry(
        "SOL-USD", snap, sentiment=0.90, rsi=30.0, is_new_pair=True, policy=pol
    )
    assert sol.allowed is False
    assert any("not_eligible" in r or "quality_tryout" in r for r in sol.reasons), sol.reasons
    uni = evaluate_buy_entry(
        "UNI-USD", snap, sentiment=0.90, rsi=30.0, is_new_pair=True, policy=pol
    )
    assert uni.allowed is False


def test_recovery_cap_clamps_bull_sleeve():
    pol = json.loads(json.dumps(load_policy()))
    oo = pol.setdefault("operator_override", {})
    rec = oo.setdefault("recovery_soft_down_20260828", {})
    rec["enabled"] = True
    rec["bull_rebalance_cap_usd_max"] = 75.0
    rec["new_alt_policy"] = "quality_tryout"
    from phase6.core.regime_cash_policy import apply_recovery_cap_to_snapshot

    snap = _soft_snap(rebalance_cap_usd=100.0, regime_layer="soft_down", regime="soft_down")
    out = apply_recovery_cap_to_snapshot(snap, policy=pol)
    assert out.rebalance_cap_usd == 75.0, out.rebalance_cap_usd


if __name__ == "__main__":
    test_collect_live_config_includes_uni_rave()
    test_evaluate_blocks_uni_even_bull_good_signals()
    test_evaluate_blocks_rave()
    test_btc_not_on_explicit_block_list()
    test_recovery_allowlist_blocks_new_alt_when_soft_down_snap()
    test_quality_tryout_allows_link_blocks_sol()
    test_recovery_cap_clamps_bull_sleeve()
    print("PASS isolation buy_block_pairs")
