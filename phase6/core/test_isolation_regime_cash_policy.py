#!/usr/bin/env python3
"""Isolation: REGIME-CASH policy — park blocks buys; flat B gated deploy; bull entry gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import (
    evaluate_buy_entry,
    filter_trade_plan_regime_cash,
    load_policy,
    resolve_regime_cash,
)


def test_bear_park_blocks_buy():
    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "bear", "confidence": 1.0, "btc_return_pct": -15.0},
    )
    assert snap.strategy_mode == "usdc_park" or snap.allow_new_buys is False
    dec = evaluate_buy_entry(
        "SOL-USD",
        snap,
        sentiment=0.9,
        rsi=30.0,
        lockout_pairs=set(),
    )
    assert dec.allowed is False
    assert any("park" in r or "allow_new_buys" in r for r in dec.reasons)


def test_bull_entry_requires_rsi_and_sentiment():
    pol = load_policy()
    # Force bull deploy without relying on knob merge for sentiment path
    pol = json.loads(json.dumps(pol))
    pol["regimes"]["bull"]["strategy_mode"] = "deploy"
    pol["regimes"]["bull"]["allow_new_buys"] = True
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "bull", "confidence": 1.0, "btc_return_pct": 20.0},
    )
    # Overbought should fail
    bad = evaluate_buy_entry("ETH-USD", snap, sentiment=0.5, rsi=85.0)
    assert bad.allowed is False
    assert any("rsi" in r for r in bad.reasons)
    # Good entry
    good = evaluate_buy_entry("ETH-USD", snap, sentiment=0.5, rsi=50.0)
    assert good.allowed is True


def test_lockout_blocks_even_in_bull():
    pol = load_policy()
    pol = json.loads(json.dumps(pol))
    pol["regimes"]["bull"]["allow_new_buys"] = True
    pol["regimes"]["bull"]["strategy_mode"] = "deploy"
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "bull", "confidence": 1.0, "btc_return_pct": 20.0},
    )
    dec = evaluate_buy_entry(
        "OP-USD",
        snap,
        sentiment=0.8,
        rsi=40.0,
        lockout_pairs={"OP-USD"},
    )
    assert dec.allowed is False
    assert "lockout_active" in dec.reasons


def test_filter_plan_enforces_bear_park():
    """Park path: use bear (flat is option-B deploy as of 2026-07-18)."""
    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "bear", "confidence": 1.0, "btc_return_pct": -12.0},
    )
    snap.enforce = True
    plan = SimpleNamespace(
        actions=[
            {"pair": "BTC-USD", "action": "SELL", "usd": 50},
            {"pair": "SOL-USD", "action": "BUY", "usd": 100},
        ]
    )
    filter_trade_plan_regime_cash(
        plan,
        snap,
        sentiment_scores={"SOL-USD": 0.9},
        rsi_values={"SOL-USD": 40.0},
        lockout_pairs=set(),
        held_pairs=set(),
        enforce=True,
    )
    actions = [a["action"] for a in plan.actions]
    assert "SELL" in actions
    assert "BUY" not in actions


def test_flat_option_b_gated_deploy():
    """Flat thaw: allow gated buys; still block overbought RSI."""
    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "flat", "confidence": 1.0, "btc_return_pct": 2.0},
    )
    assert snap.strategy_mode == "deploy"
    assert snap.allow_new_buys is True
    assert float(snap.rebalance_cap_usd) > 0
    assert float(snap.rebalance_cap_usd) <= 100.0

    ok = evaluate_buy_entry("SOL-USD", snap, sentiment=0.40, rsi=45.0)
    assert ok.allowed is True, ok.reasons

    hot = evaluate_buy_entry("SOL-USD", snap, sentiment=0.40, rsi=70.0)
    assert hot.allowed is False
    assert any("rsi" in r for r in hot.reasons)

    weak = evaluate_buy_entry("SOL-USD", snap, sentiment=0.05, rsi=40.0)
    assert weak.allowed is False
    assert any("sentiment" in r for r in weak.reasons)

    plan = SimpleNamespace(
        actions=[
            {"pair": "BTC-USD", "action": "SELL", "usd": 50},
            {"pair": "SOL-USD", "action": "BUY", "usd": 100},
            {"pair": "ETH-USD", "action": "BUY", "usd": 100},
        ]
    )
    filter_trade_plan_regime_cash(
        plan,
        snap,
        sentiment_scores={"SOL-USD": 0.4, "ETH-USD": 0.4},
        rsi_values={"SOL-USD": 45.0, "ETH-USD": 72.0},
        lockout_pairs=set(),
        held_pairs=set(),
        enforce=True,
    )
    pairs = [(a["pair"], a["action"]) for a in plan.actions]
    assert ("BTC-USD", "SELL") in pairs
    assert ("SOL-USD", "BUY") in pairs
    assert ("ETH-USD", "BUY") not in pairs


def test_hard_exit_shadow_only():
    from phase6.core.regime_cash_policy import (
        apply_hard_exit_to_plan,
        build_hard_exit_sell_actions,
        hard_exit_reasons,
        prefer_exit,
        resolve_regime_cash,
        load_policy,
    )
    import tempfile
    from pathlib import Path

    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "transition", "confidence": 1.0, "btc_return_pct": 11.0},
    )
    # Force overbought on LINK
    dec = prefer_exit("LINK-USD", snap, sentiment=0.5, rsi=80.0)
    hard = hard_exit_reasons(dec.reasons)
    assert hard, dec.reasons
    assert not any("park_prefer" in h for h in hard)

    acts = build_hard_exit_sell_actions(
        {"LINK-USD": 500.0, "SOL-USD": 100.0},
        snap,
        sentiment_scores={"LINK-USD": 0.5, "SOL-USD": 0.5},
        rsi_values={"LINK-USD": 80.0, "SOL-USD": 40.0},
        min_sell_usd=25.0,
    )
    pairs = [a["pair"] for a in acts]
    assert "LINK-USD" in pairs
    assert "SOL-USD" not in pairs  # only park soft at most

    plan = SimpleNamespace(actions=[{"pair": "BTC-USD", "action": "SELL", "usd": 10}])
    with tempfile.TemporaryDirectory() as td:
        logp = Path(td) / "shadow.json"
        apply_hard_exit_to_plan(
            plan,
            snap,
            {"LINK-USD": 500.0},
            sentiment_scores={"LINK-USD": 0.5},
            rsi_values={"LINK-USD": 80.0},
            hard_cfg={
                "enabled": True,
                "shadow_only": True,
                "live_apply": False,
                "operator_approve": True,
                "notify_telegram": False,
                "min_sell_usd": 25.0,
                "max_pair_fraction": 1.0,
            },
            shadow_log_path=logp,
        )
        # shadow must NOT mutate actions with LINK sell
        assert len(plan.actions) == 1
        assert plan.actions[0]["pair"] == "BTC-USD"
        assert getattr(plan, "regime_hard_exit_proposals", None)
        assert logp.exists()
        body = json.loads(logp.read_text())
        assert body["shadow_only"] is True
        assert body["n"] >= 1


def test_hard_exit_never_park_soft():
    from phase6.core.regime_cash_policy import (
        build_hard_exit_sell_actions,
        prefer_exit,
        hard_exit_reasons,
        resolve_regime_cash,
        load_policy,
    )

    pol = load_policy()
    snap = resolve_regime_cash(
        policy=pol,
        detection={"regime": "transition", "confidence": 1.0, "btc_return_pct": 11.0},
    )
    assert snap.strategy_mode == "usdc_park" or snap.allow_new_buys is False
    dec = prefer_exit("LINK-USD", snap, sentiment=0.5, rsi=40.0)
    # may include park_prefer_reduce only
    assert not hard_exit_reasons(dec.reasons), dec.reasons
    acts = build_hard_exit_sell_actions(
        {"LINK-USD": 1200.0},
        snap,
        sentiment_scores={"LINK-USD": 0.5},
        rsi_values={"LINK-USD": 40.0},
    )
    assert acts == []


if __name__ == "__main__":
    test_bear_park_blocks_buy()
    test_bull_entry_requires_rsi_and_sentiment()
    test_lockout_blocks_even_in_bull()
    test_filter_plan_enforces_bear_park()
    test_flat_option_b_gated_deploy()
    test_hard_exit_shadow_only()
    test_hard_exit_never_park_soft()
    print("regime_cash_policy isolation PASS")
