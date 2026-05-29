#!/usr/bin/env python3
"""
R-003: Layer 1 - Inverse Volatility + Liquidity Bias Only

No sentiment, no holding proportional bias.
Tests the isolated value of adding liquidity bias to inverse volatility.
"""

import sys
import json
from pathlib import Path
import math

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.allocation.enhanced_allocation_engine import apply_liquidity_bias

PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
DATA_DIR = Path("/home/brad/projects/crypto-trading-bot/backtests/data")


def load_historical_data():
    data = {}
    for pair in PAIRS:
        symbol = pair.split("-")[0].lower()
        file_path = DATA_DIR / f"backtest_historical_ohlcv_{symbol}_2025-04-20_to_2026-04-20.json"
        if file_path.exists():
            with open(file_path) as f:
                raw = json.load(f)
            cleaned = []
            for row in raw:
                cleaned.append({
                    "timestamp": row.get("timestamp") or row.get("time"),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0))
                })
            data[pair] = sorted(cleaned, key=lambda x: x["timestamp"])
            print(f"  Loaded {pair}: {len(data[pair])} rows")
    return data


def compute_simple_inv_vol(prices_list, window=20):
    if len(prices_list) < window + 1:
        return {p: 1.0 / len(PAIRS) for p in PAIRS}
    
    returns = []
    for i in range(1, min(window + 1, len(prices_list))):
        ret = (prices_list[-i]["close"] - prices_list[-i-1]["close"]) / prices_list[-i-1]["close"]
        returns.append(ret)
    
    if not returns:
        return {p: 1.0 / len(PAIRS) for p in PAIRS}
    
    vol = math.sqrt(sum(r * r for r in returns) / len(returns))
    if vol == 0:
        vol = 0.01
    inv_vol = 1.0 / vol
    return {p: inv_vol for p in PAIRS}


def run_layer1_backtest():
    print("=" * 75)
    print("R-003: LAYER 1 - INVERSE VOL + LIQUIDITY BIAS")
    print("=" * 75)

    print("\n[1] Loading historical OHLCV data...")
    hist_data = load_historical_data()

    print("\n[2] Running Inverse Vol + Liquidity Bias simulation (last 120 days)...")
    portfolio_value = 10000.0
    current_holdings = {p: 1.0 / len(PAIRS) for p in PAIRS}

    btc_data = hist_data.get("BTC-USD", [])
    test_data = btc_data[-120:]

    for i, row in enumerate(test_data):
        date = row["timestamp"][:10]

        # Inverse volatility base
        base_weights = {}
        total_inv = 0
        for p in PAIRS:
            if p in hist_data:
                recent = hist_data[p][-25:]
                w = compute_simple_inv_vol(recent)
                base_weights[p] = w.get(p, 1.0)
                total_inv += base_weights[p]
        
        if total_inv > 0:
            base_weights = {p: v / total_inv for p, v in base_weights.items()}

        # Liquidity bias only (no sentiment, no holding bias)
        liq_scores = {}
        for p in PAIRS:
            vols = [d["volume"] for d in hist_data.get(p, [])[-20:]]
            avg_vol = sum(vols) / len(vols) if vols else 1
            liq_scores[p] = min(1.0, avg_vol / 5e8)

        final_weights = apply_liquidity_bias(base_weights, liq_scores, liquidity_weight=0.3)

        # Daily return
        daily_ret = 0.0
        for p in PAIRS:
            if p in hist_data and len(hist_data[p]) > 1:
                curr = hist_data[p][-1]["close"]
                prev = hist_data[p][-2]["close"]
                ret = (curr - prev) / prev if prev > 0 else 0
                daily_ret += final_weights.get(p, 0) * ret

        portfolio_value *= (1 + daily_ret)
        current_holdings = final_weights

        if (i + 1) % 20 == 0:
            print(f"  {date}: ${portfolio_value:,.2f}")

    print("\n" + "=" * 75)
    print(f"Final Value: ${portfolio_value:,.2f}")
    print(f"Return: {(portfolio_value / 10000 - 1) * 100:.2f}%")
    print("=" * 75)

    return portfolio_value


if __name__ == "__main__":
    run_layer1_backtest()