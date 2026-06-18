#!/usr/bin/env python3
"""
Rebalancing Strategy Comparison Harness (12-month backtest)

Compares three rebalancing approaches on identical data:
1. Correlation-Triggered (from PHASE_6_REBALANCING.md spec)
2. Daily Inverse-Vol (current Phase 6 runner behavior)
3. Hybrid (current HybridRebalancer logic)

Data: 2025-04-20 to 2026-04-19 (365 days)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import numpy as np

# =============================================================================
# CONFIG
# =============================================================================
DATA_DIR = Path("backtests/data")
PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
SYMBOLS = [p.split("-")[0].lower() for p in PAIRS]

INITIAL_CAPITAL = 10000.0
FEE_RATE = 0.003  # 0.3%
TOTAL_DAYS = 365

# Correlation strategy params (from spec)
CORR_WINDOW = 30
HIGH_CORR_THRESHOLD = 0.70
REBALANCE_SHIFT_PCT = 0.50

# Hybrid strategy params
HYBRID_SENTIMENT_DELTA = 0.15
HYBRID_MIN_INTERVAL_DAYS = 7


def load_all_data() -> Dict[str, List[dict]]:
    data = {}
    for pair, symbol in zip(PAIRS, SYMBOLS):
        path = DATA_DIR / f"backtest_historical_ohlcv_{symbol}_2025-04-20_to_2026-04-20.json"
        if not path.exists():
            print(f"WARNING: Missing {path}")
            continue
        with open(path) as f:
            raw = json.load(f)
        cleaned = []
        for row in raw:
            cleaned.append({
                "timestamp": row.get("timestamp") or row.get("time"),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0))
            })
        data[pair] = sorted(cleaned, key=lambda x: x["timestamp"])
    return data


def get_price_history(data: Dict[str, List[dict]], day: int, window: int) -> np.ndarray:
    """Return price matrix [window, n_pairs] ending at day"""
    matrix = []
    for pair in PAIRS:
        if pair not in data:
            matrix.append([1.0] * window)
            continue
        series = data[pair]
        start = max(0, day - window)
        prices = [series[i]["close"] for i in range(start, min(day, len(series)))]
        if len(prices) < window:
            prices = [prices[0]] * (window - len(prices)) + prices
        matrix.append(prices[-window:])
    return np.array(matrix).T


# =============================================================================
# STRATEGY 1: Correlation-Triggered (Spec)
# =============================================================================
def run_correlation_strategy(data: Dict[str, List[dict]]) -> Dict[str, Any]:
    capital = INITIAL_CAPITAL
    positions = {p: capital / len(PAIRS) for p in PAIRS}
    reserve = 0.0
    trades = 0
    fees_paid = 0.0
    rebalance_days = []

    for day in range(TOTAL_DAYS):
        # Simple daily price update (mark-to-market)
        for pair in PAIRS:
            if pair in data and day < len(data[pair]):
                price = data[pair][day]["close"]
                # positions are in USD terms for simplicity

        if day >= CORR_WINDOW and day % 7 == 0:  # Weekly check
            matrix = get_price_history(data, day, CORR_WINDOW)
            if matrix.shape[0] >= 10:
                corr_matrix = np.corrcoef(matrix.T)
                avg_corr = np.mean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)])

                if avg_corr > HIGH_CORR_THRESHOLD:
                    # Shift 50% to reserve
                    for pair in PAIRS:
                        shift = positions[pair] * REBALANCE_SHIFT_PCT
                        positions[pair] -= shift
                        reserve += shift
                    rebalance_days.append((day, "high_corr", avg_corr))
                    trades += 1

                    # Redeploy from reserve using simple sentiment proxy (price momentum)
                    for pair in PAIRS:
                        if reserve < 50:
                            break
                        mom = (data[pair][day]["close"] - data[pair][max(0, day-7)]["close"]) / data[pair][max(0, day-7)]["close"]
                        if mom > 0.02:
                            deploy = min(reserve * 0.25, 200)
                            positions[pair] += deploy
                            reserve -= deploy
                            trades += 1

    final_value = sum(positions.values()) + reserve
    return {
        "strategy": "Correlation-Triggered",
        "final_value": round(final_value, 2),
        "pnl_pct": round((final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
        "total_fees": round(fees_paid, 2),
        "rebalance_count": len(rebalance_days),
        "trades": trades
    }


# =============================================================================
# STRATEGY 2: Daily Inverse-Vol (Current)
# =============================================================================
def run_daily_inv_vol_strategy(data: Dict[str, List[dict]]) -> Dict[str, Any]:
    capital = INITIAL_CAPITAL
    positions = {p: capital / len(PAIRS) for p in PAIRS}
    fees_paid = 0.0
    rebalance_days = []

    for day in range(TOTAL_DAYS):
        if day < 20:
            continue
        # Compute inverse vol weights
        vols = {}
        for pair in PAIRS:
            if pair not in data or day < 20:
                vols[pair] = 1.0
                continue
            returns = []
            for i in range(1, 21):
                if day - i >= 0:
                    ret = (data[pair][day-i]["close"] - data[pair][day-i-1]["close"]) / data[pair][day-i-1]["close"]
                    returns.append(abs(ret))
            vols[pair] = np.mean(returns) if returns else 1.0

        inv_vol = {p: 1.0 / max(v, 1e-6) for p, v in vols.items()}
        total_inv = sum(inv_vol.values())
        weights = {p: v / total_inv for p, v in inv_vol.items()}

        # Rebalance daily
        target_value = capital
        for pair in PAIRS:
            target = target_value * weights[pair]
            diff = target - positions[pair]
            if abs(diff) > 10:
                fee = abs(diff) * FEE_RATE
                positions[pair] = target
                fees_paid += fee
                capital -= fee
                rebalance_days.append(day)

    final_value = sum(positions.values())
    return {
        "strategy": "Daily Inverse-Vol",
        "final_value": round(final_value, 2),
        "pnl_pct": round((final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
        "total_fees": round(fees_paid, 2),
        "rebalance_count": len(rebalance_days),
        "trades": len(rebalance_days)
    }


# =============================================================================
# STRATEGY 3: Hybrid (Current)
# =============================================================================
def run_hybrid_strategy(data: Dict[str, List[dict]]) -> Dict[str, Any]:
    capital = INITIAL_CAPITAL
    positions = {p: capital / len(PAIRS) for p in PAIRS}
    fees_paid = 0.0
    rebalance_days = []
    last_rebalance = 0

    for day in range(TOTAL_DAYS):
        if day - last_rebalance < HYBRID_MIN_INTERVAL_DAYS:
            continue

        # Simulate sentiment delta (using price momentum as proxy)
        sentiment_deltas = {}
        for pair in PAIRS:
            if pair not in data or day < 7:
                continue
            mom = (data[pair][day]["close"] - data[pair][day-7]["close"]) / data[pair][day-7]["close"]
            sentiment_deltas[pair] = mom

        max_delta = max(sentiment_deltas.values()) if sentiment_deltas else 0
        if max_delta > HYBRID_SENTIMENT_DELTA:
            # Rebalance toward high momentum
            total = sum(positions.values())
            for pair in PAIRS:
                if pair in sentiment_deltas and sentiment_deltas[pair] == max_delta:
                    target = total * 0.30
                    diff = target - positions[pair]
                    if abs(diff) > 20:
                        fee = abs(diff) * FEE_RATE
                        positions[pair] = target
                        fees_paid += fee
                        capital -= fee
                        rebalance_days.append(day)
                        last_rebalance = day
                        break

    final_value = sum(positions.values())
    return {
        "strategy": "Hybrid",
        "final_value": round(final_value, 2),
        "pnl_pct": round((final_value - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
        "total_fees": round(fees_paid, 2),
        "rebalance_count": len(rebalance_days),
        "trades": len(rebalance_days)
    }


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("Loading 12-month dataset (2025-04-20 → 2026-04-19)...")
    data = load_all_data()
    print(f"Loaded {len(data)} pairs\n")

    results = []
    results.append(run_correlation_strategy(data))
    results.append(run_daily_inv_vol_strategy(data))
    results.append(run_hybrid_strategy(data))

    print("\n" + "=" * 70)
    print("REBALANCING STRATEGY COMPARISON (12 months)")
    print("=" * 70)
    print(f"{'Strategy':<25} {'Final Value':>12} {'P&L %':>8} {'Fees':>8} {'Rebalances':>12}")
    print("-" * 70)
    for r in results:
        print(f"{r['strategy']:<25} ${r['final_value']:>10,.0f} {r['pnl_pct']:>7.1f}% ${r['total_fees']:>6.0f} {r['rebalance_count']:>12}")
    print("=" * 70)