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


if __name__ == "__main__":
    test_collect_live_config_includes_uni_rave()
    test_evaluate_blocks_uni_even_bull_good_signals()
    test_evaluate_blocks_rave()
    test_btc_not_on_explicit_block_list()
    test_recovery_allowlist_blocks_new_alt_when_soft_down_snap()
    print("PASS isolation buy_block_pairs")
