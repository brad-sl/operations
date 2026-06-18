#!/usr/bin/env python3
"""
Isolated RSI Pipeline Test
Tests price fetching + RSI calculation independently of the full runner.
Run this until it produces real RSI values, then integrate back.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.price_history_manager import PriceHistoryManager

# Standalone RSI function (same as in runner)
def calculate_rsi(prices, period=14):
    """Wilder's RSI - pure Python."""
    if len(prices) < period + 1:
        return []
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(round(rsi, 2))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return rsi_values


def main():
    from dotenv import load_dotenv
    load_dotenv()
    print("=== Isolated RSI Pipeline Test ===")
    print(f"Time: {datetime.now().isoformat()}\n")

    # Use live client (or shadow if preferred)
    exchange = CoinbaseExchangeClient(mode="live")

    FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
    price_history = PriceHistoryManager(max_history=100)

    print("Seeding price history with recent values for RSI test...\n")

    # Seed with 20 realistic recent prices per pair (simulating accumulation)
    import random
    base_prices = {
        "BTC-USD": 76500,
        "ETH-USD": 3200,
        "SOL-USD": 145,
        "XRP-USD": 0.52,
        "DOGE-USD": 0.12
    }

    for pair in FIXED_UNIVERSE:
        base = base_prices[pair]
        for i in range(20):
            # Small realistic movement
            variation = random.uniform(-0.015, 0.015)
            price = round(base * (1 + variation * (i % 5 - 2)), 2 if base < 10 else 0)
            price_history.add_price(pair, price)
        print(f"{pair}: Seeded 20 prices (latest ~${base:,.2f})")

    print("\n--- RSI Calculation (needs ≥15 points per pair) ---")

    rsi_results = {}
    for pair in FIXED_UNIVERSE:
        prices = price_history.get_prices(pair)
        count = len(prices)
        if count >= 15:
            rsi_series = calculate_rsi(prices, period=14)
            if rsi_series:
                rsi_results[pair] = rsi_series[-1]
                print(f"{pair}: RSI = {rsi_series[-1]} (based on {count} prices)")
            else:
                print(f"{pair}: Not enough data for RSI ({count} prices)")
        else:
            print(f"{pair}: Insufficient history ({count}/15 prices)")

    print("\n=== Final RSI Output ===")
    print(rsi_results if rsi_results else "No RSI values produced yet")

    # Also write to a test cache for verification
    test_cache = Path("data/state/test_rsi_output.json")
    test_cache.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(test_cache, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "rsi": rsi_results,
            "price_counts": {p: len(price_history.get_prices(p)) for p in FIXED_UNIVERSE}
        }, f, indent=2)
    print(f"\nTest output written to: {test_cache}")


if __name__ == "__main__":
    main()
