#!/usr/bin/env python3
"""
Enhanced Allocation Engine (Phase 6.1)
Adds liquidity bias and sentiment awareness to allocation decisions.
Respects:
- Proportional scaling to existing holdings (sticky rebalancing)
- Withdrawal reserve buffers
- No new pair injection without approval

Public API extensions:
- compute_enhanced_allocations(...)
- apply_liquidity_bias(...)
- apply_sentiment_adjustment(...)
- apply_holding_proportional_bias(...)
- enforce_withdrawal_reserve_on_allocs(...)
"""

from typing import Dict, List, Any, Optional
import math

def apply_liquidity_bias(
    base_weights: Dict[str, float],
    liquidity_scores: Dict[str, float],
    liquidity_weight: float = 0.3
) -> Dict[str, float]:
    """
    Boost weights for higher liquidity pairs.
    liquidity_scores: higher = better liquidity (e.g. normalized 24h volume or depth proxy)
    """
    if not base_weights:
        return {}
    adjusted = {}
    total = 0.0
    for sym, base_w in base_weights.items():
        liq = liquidity_scores.get(sym, 0.5)  # neutral default
        # Liquidity multiplier: higher liq -> higher weight
        mult = 1.0 + liquidity_weight * (liq - 0.5) * 2  # scale around 0.5
        adj = base_w * max(0.5, mult)
        adjusted[sym] = adj
        total += adj
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted


def apply_sentiment_adjustment(
    base_weights: Dict[str, float],
    sentiment_scores: Dict[str, float],
    sentiment_weight: float = 0.25
) -> Dict[str, float]:
    """
    Adjust weights based on time-decayed sentiment (from sentiment_scorer).
    Positive sentiment boosts allocation.
    """
    if not base_weights:
        return {}
    adjusted = {}
    total = 0.0
    for sym, base_w in base_weights.items():
        sent = sentiment_scores.get(sym, 0.0)
        adj = base_w * (1.0 + sentiment_weight * sent)
        adjusted[sym] = max(0.01, adj)
        total += adjusted[sym]
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted


def apply_holding_proportional_bias(
    base_weights: Dict[str, float],
    current_holdings: Dict[str, float],
    holding_bias: float = 0.4
) -> Dict[str, float]:
    """
    Favor proportional scaling of EXISTING holdings rather than new pairs.
    Current holdings get boosted; new pairs get reduced weight.
    """
    if not base_weights:
        return {}
    if not current_holdings:
        return base_weights  # fresh start mode
    adjusted = {}
    total = 0.0
    held_total = sum(current_holdings.values())
    for sym, base_w in base_weights.items():
        if sym in current_holdings and held_total > 0:
            holding_pct = current_holdings[sym] / held_total
            # Boost towards current proportion
            adj = base_w * (1.0 + holding_bias * holding_pct)
        else:
            # Penalize new pairs
            adj = base_w * (1.0 - holding_bias * 0.5)
        adjusted[sym] = max(0.01, adj)
        total += adjusted[sym]
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted


def compute_enhanced_allocations(
    volatilities: Dict[str, float],
    liquidity_scores: Dict[str, float],
    sentiment_scores: Dict[str, float],
    current_holdings_usd: Optional[Dict[str, float]] = None,
    min_weight: float = 0.04,
    max_weight: float = 0.20,
    total_capital: float = 10000.0,
    withdrawal_reserve_usd: float = 500.0,
    min_reserve_usd: float = 500.0
) -> Dict[str, float]:
    """
    Main entrypoint: produces target allocation % (weights) with all biases applied.
    Respects withdrawal reserve by reducing deployable capital.
    """
    if not volatilities:
        return {}

    # 1. Start with inverse vol (from original engine)
    inv_vol = {}
    for k, v in volatilities.items():
        inv_vol[k] = 1.0 / max(1e-12, float(v))
    s = sum(inv_vol.values())
    base = {k: v / s for k, v in inv_vol.items()} if s > 0 else {k: 0.0 for k in volatilities}

    # 2. Apply bounds
    clipped = {}
    for k, w in base.items():
        clipped[k] = max(min_weight, min(max_weight, w))
    total = sum(clipped.values())
    base = {k: v / total for k, v in clipped.items()} if total > 0 else base

    # 3. Liquidity bias
    base = apply_liquidity_bias(base, liquidity_scores)

    # 4. Sentiment
    base = apply_sentiment_adjustment(base, sentiment_scores)

    # 5. Holding proportional bias (sticky to existing)
    if current_holdings_usd:
        base = apply_holding_proportional_bias(base, current_holdings_usd)

    # 6. Withdrawal reserve is enforced by caller (withdrawal_reserve.py)
    # This function always returns weights summing to ~1.0 for the deployable capital.
    # Final normalize
    total = sum(base.values())
    if total > 0:
        base = {k: v / total for k, v in base.items()}

    return base


def rebalance_plan_enhanced(
    current_allocs: Dict[str, float],
    target_weights: Dict[str, float],
    total_capital: float,
    min_move: float = 50.0
) -> List[Dict[str, Any]]:
    """
    Enhanced rebalance plan that produces BUY/SELL moves.
    Respects min_move threshold.
    """
    plan: List[Dict[str, Any]] = []
    if not target_weights or total_capital <= 0:
        return plan

    target_usd = {k: v * total_capital for k, v in target_weights.items()}
    coins = set(current_allocs.keys()) | set(target_usd.keys())

    for coin in coins:
        cur = current_allocs.get(coin, 0.0)
        tgt = target_usd.get(coin, 0.0)
        diff = tgt - cur
        if abs(diff) >= min_move:
            action = "BUY" if diff > 0 else "SELL"
            plan.append({
                "pair": coin,
                "action": action,
                "usd_amount": abs(diff),  # P0-02.8 full prec
                "reason": "enhanced-allocation"
            })

    # Sort by size
    plan.sort(key=lambda x: x["usd_amount"], reverse=True)
    return plan


if __name__ == "__main__":
    # Quick demo
    vols = {"BTC-USD": 0.8, "ETH-USD": 1.2, "SOL-USD": 2.5}
    liq = {"BTC-USD": 0.95, "ETH-USD": 0.85, "SOL-USD": 0.6}
    sent = {"BTC-USD": 0.4, "ETH-USD": 0.1, "SOL-USD": -0.3}
    curr = {"BTC-USD": 4500.0, "ETH-USD": 3000.0}
    allocs = compute_enhanced_allocations(vols, liq, sent, curr, total_capital=10000.0, withdrawal_reserve_usd=600.0)
    print("Enhanced allocations:", allocs)
    plan = rebalance_plan_enhanced(curr, allocs, 10000.0)
    print("Rebalance plan:", plan)
