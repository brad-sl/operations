# See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths, state, config hygiene and drift prevention.
# All code must derive PROJECT_ROOT via paths.py and avoid absolute hardcodes.

# allocation_engine.py - Lightweight portfolio rebalancing engine (Phase 5)
"""
Simple, codifiable helpers to calculate target allocations and rebalance plans for a multi-coin crypto portfolio.
This module is intentionally dependency-light and designed to plug into the Phase 5 bot where a dedicated rebalancer overlay is deployed.

Public API:
- compute_inverse_vol_allocations(volatilities: dict[str,float], min_weight=0.04, max_weight=0.15) -> dict[str,float]
  Returns per-coin weights that roughly equalize risk contributions via inverse volatility weighting, bounded by min/max weights, and renormalized to 1.0 total.
- plan_static_allocations(targets_pct: dict[str,float], total_capital: float) -> dict[str,float]
  Converts a user-provided target percentage map into absolute allocations (USD) given the total capital.
- rebalance_plan(current_allocs: dict[str,float], target_allocs_pct: dict[str,float], total_capital: float, min_move: float=0.0) -> list[dict]
  Produces a list of move instructions to bring the portfolio from current allocations toward target percentages. Returns a list of moves with fields: from_coin, to_coin, amount_usd.

Notes:
- This is a planning tool; actual trades must be executed through the Coinbase integration with proper authentication and fee accounting.
- This module does not perform any network I/O.
"""
from typing import Dict, List, Tuple
import math


def compute_inverse_vol_allocations(volatilities: Dict[str, float], min_weight: float = 0.04, max_weight: float = 0.15) -> Dict[str, float]:
    """Return per-coin weights in [0,1], scaled inversely by volatility and clipped to [min_weight, max_weight], then renormalized to sum to 1.0.
    vols: dict of coin -> volatility (positive float, e.g., annualized or 90d lookback). Lower = more weight.
    """
    if not volatilities:
        return {}
    # Guard against zero or negative vol
    vols = {k: max(1e-12, float(v)) for k, v in volatilities.items()}
    inv = {k: 1.0 / v for k, v in vols.items()}
    s = sum(inv.values())
    if s <= 0:
        return {k: 0.0 for k in volatilities}
    raw = {k: (v / s) for k, v in inv.items()}
    # Apply bounds
    clipped = {}
    for k, w in raw.items():
        if w < min_weight:
            clipped[k] = min_weight
        elif w > max_weight:
            clipped[k] = max_weight
        else:
            clipped[k] = w
    total = sum(clipped.values())
    if total <= 0:
        return {k: 0.0 for k in volatilities}
    # Renormalize to sum to 1.0
    normalized = {k: (v / total) for k, v in clipped.items()}
    return normalized


def plan_static_allocations(targets_pct: Dict[str, float], total_capital: float) -> Dict[str, float]:
    """Convert a target percentage map to absolute allocations in USD for a portfolio total_capital.
    Returns dict coin -> allocation_usd
    """
    allocations = {}
    if not targets_pct or total_capital <= 0:
        return allocations
    for coin, pct in targets_pct.items():
        try:
            p = float(pct) / 100.0
        except Exception:
            p = 0.0
        allocations[coin] = max(0.0, total_capital * p)
    # Normalize to exact total_capital to account for float math (P0-02.8: avoid early round-to-2 on usd; final by quantize)
    total = sum(allocations.values())
    if total > 0:
        scale = total_capital / total
        for c in allocations:
            allocations[c] = allocations[c] * scale
    return allocations


def rebalance_plan(current_allocs: Dict[str, float], target_allocs_pct: Dict[str, float], total_capital: float, min_move: float = 0.0) -> List[Dict[str, any]]:
    """Compute a rebalance plan from current allocations toward target allocations.
    Each move is a dict: {"pair": str, "action": "BUY"|"SELL", "usd_amount": float }
    Deltas are full (no artificial 25% cap) so full rebalance legs are produced when deltas large.
    min_move is the minimum USD amount to move per coin to avoid noise.
    SELL/BUY ordering is enforced at execution time (see order_executor.execute_rebalance_plan).
    """
    plan: List[Dict[str, any]] = []
    if not current_allocs or not target_allocs_pct or total_capital <= 0:
        return plan
    target_allocs_usd = plan_static_allocations(target_allocs_pct, total_capital)
    coins = set(list(current_allocs.keys()) + list(target_allocs_usd.keys()))
    # Compute deltas
    deltas = {}
    for coin in coins:
        cur_val = current_allocs.get(coin, 0.0)
        cur = cur_val.get("usd_value", cur_val) if isinstance(cur_val, dict) else cur_val
        tgt = target_allocs_usd.get(coin, 0.0)
        deltas[coin] = tgt - float(cur)
    # Sort by magnitude of delta (for logging/diagnostics; exec layer forces SELL-first atomic)
    moves = []
    for coin, diff in deltas.items():
        if abs(diff) >= max(min_move, 1e-6):
            moves.append((coin, diff))  # positive diff = need to buy, negative = sell
    moves.sort(key=lambda x: abs(x[1]), reverse=True)
    # Emit full-delta moves (P0-02.7: no 0.25*total cap; quantize happens in executor)
    for coin, diff in moves:
        amt = abs(diff)
        action = "SELL" if diff < 0 else "BUY"
        plan.append({"pair": coin, "action": action, "usd_amount": amt})
    return plan

# Simple convenience for quick testing in interactive sessions
if __name__ == '__main__':
    # Example usage (example numbers only)
    curr = {'XRP': 1500.0, 'DOGE': 1200.0, 'SHIB': 1600.0}
    targ = {'XRP': 20, 'DOGE': 15, 'SHIB': 15}
    total = 5000
    print(rebalance_plan(curr,targ,total))
