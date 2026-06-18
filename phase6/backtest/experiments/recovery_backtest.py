#!/usr/bin/env python3
"""
Isolated backtest: Post-stop-loss recovery scenario
Tests the impact of the top 3 proposed rebalancing enhancements
when the basket is reduced to only 2 pairs + large idle cash.
"""

from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
from pathlib import Path

# Reuse existing modules
from phase6.backtest.data_loader import DailyDataLoader
from phase6.backtest.pair_selector import PairCandidate, select_new_pairs
from phase6.scripts.deploy_capital import deploy_capital

FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"]


@dataclass
class RecoveryConfig:
    name: str
    rebalance_cap_usd: float = 500.0
    dynamic_cap_when_low: bool = False
    relax_sentiment_when_low: bool = False
    rsi_fallback: bool = False
    min_new_pair_sentiment: float = 0.20


def load_real_sentiment() -> Dict[str, float]:
    """Use the real sentiment cache from the project."""
    cache_path = Path("sentiment_cache.json")
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        return {k: v.get("sentiment", 0.0) for k, v in data.items()}
    # Fallback neutral
    return {p: 0.0 for p in FIXED_UNIVERSE}


def simulate_recovery(cfg: RecoveryConfig, days: int = 60) -> dict:
    """Simulate daily rebalancing starting from only 2 pairs + large cash."""
    loader = DailyDataLoader()
    price_data = loader.load_universe(FIXED_UNIVERSE)

    # Starting state: only ETH + XRP (post stop-loss)
    positions = {
        "ETH-USD": 133.86,
        "XRP-USD": 20.28,
    }
    cash = 613.72
    equity_curve = []
    pairs_held_over_time = []
    trades = []

    sentiment_scores = load_real_sentiment()
    rsi_values = {p: 45 for p in FIXED_UNIVERSE}  # assume neutral RSI > 30

    start_date = date(2025, 4, 20)
    current = start_date

    for day in range(days):
        day_key = current
        # Mark to market
        portfolio_value = cash
        for pair, usd_value in positions.items():
            df = price_data.get(pair)
            if df is not None and day_key in df.index:
                close = float(df.loc[day_key, "close"])
                # crude conversion back to amount (we only track USD value here for simplicity)
                portfolio_value += usd_value
            else:
                portfolio_value += usd_value
        equity_curve.append(portfolio_value)
        pairs_held_over_time.append(len(positions))

        # === Rebalance logic (the part we're testing) ===
        rebalance_cap = cfg.rebalance_cap_usd
        if cfg.dynamic_cap_when_low and len(positions) < 3:
            rebalance_cap = 900.0

        min_sent = 0.20
        if cfg.relax_sentiment_when_low and len(positions) < 3:
            min_sent = 0.0

        new_alloc = deploy_capital(
            current_allocations=positions,
            new_capital=min(rebalance_cap, cash),
            sentiment_scores=sentiment_scores,
            source="reserve",
            candidate_pairs=FIXED_UNIVERSE,
            rsi_values=rsi_values if not cfg.rsi_fallback else None,
            min_rsi=30.0,
            min_new_pair_sentiment=min_sent,
            allow_new_pairs=True,
        )

        # Simple update: apply new allocations
        for pair, target_usd in new_alloc.items():
            if pair not in positions:
                trades.append({"date": current, "pair": pair, "action": "ADD"})
            positions[pair] = target_usd

        # Remove pairs that went to zero
        positions = {k: v for k, v in positions.items() if v > 5.0}
        cash = max(0.0, portfolio_value - sum(positions.values()))

        current = current.fromordinal(current.toordinal() + 1)

    final_equity = equity_curve[-1] if equity_curve else 0
    max_dd = max(0, (max(equity_curve) - min(equity_curve)) / max(equity_curve) * 100) if equity_curve else 0

    return {
        "name": cfg.name,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity / 767.86 - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_pairs_held": round(sum(pairs_held_over_time) / len(pairs_held_over_time), 1),
        "trades_executed": len(trades),
        "final_pairs": list(positions.keys()),
    }


if __name__ == "__main__":
    print("=== Post-Stop-Loss Recovery Backtest ===\n")

    configs = [
        RecoveryConfig("Baseline (current)", rebalance_cap_usd=500.0),
        RecoveryConfig("1. Dynamic high cap when <3 pairs", dynamic_cap_when_low=True),
        RecoveryConfig("2. Relaxed sentiment when <3 pairs", relax_sentiment_when_low=True),
        RecoveryConfig("3. RSI fallback + dynamic cap", dynamic_cap_when_low=True, rsi_fallback=True),
        RecoveryConfig("Combined (1+2+3)", dynamic_cap_when_low=True, relax_sentiment_when_low=True, rsi_fallback=True),
    ]

    results = []
    for cfg in configs:
        res = simulate_recovery(cfg, days=180)
        results.append(res)
        print(f"{cfg.name}:")
        print(f"  Final Equity: ${res['final_equity']:.2f} ({res['total_return_pct']:+.1f}%)")
        print(f"  Max DD: {res['max_drawdown_pct']:.1f}% | Avg pairs: {res['avg_pairs_held']}")
        print(f"  Trades: {res['trades_executed']} | Final basket: {res['final_pairs']}\n")

    print("=== Summary ===")
    best = max(results, key=lambda x: x["final_equity"])
    print(f"Best performer: {best['name']} → ${best['final_equity']:.2f}")
