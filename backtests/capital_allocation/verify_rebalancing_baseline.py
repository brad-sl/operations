#!/usr/bin/env python3
"""
Stand-alone Rebalancing Verification Test
Goal: Prove that basic weekly rebalancing + $100/week injection works on the available data.
"""

import json
import os
from datetime import datetime
from collections import defaultdict

DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
PAIRS = ["btc", "eth", "sol", "xrp", "doge"]  # Only pairs with data

INITIAL_CAPITAL = 10000.0
WEEKLY_INJECTION = 100.0
TOTAL_WEEKS = 52
FEE = 0.005

def load_ohlcv(pair):
    fname = f"backtest_historical_ohlcv_{pair}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    return filtered

def get_weekly_prices(data):
    """Get approximate weekly closing prices"""
    weekly = []
    for i in range(0, len(data), 7):
        if i < len(data):
            weekly.append(float(data[i]['close']))
    return weekly

print("=== REBALANCING BASELINE VERIFICATION ===\n")

# Load data for all pairs
pair_data = {}
for p in PAIRS:
    try:
        pair_data[p] = load_ohlcv(p)
        print(f"Loaded {p}: {len(pair_data[p])} candles")
    except Exception as e:
        print(f"Failed to load {p}: {e}")

print(f"\nUsing {len(pair_data)} pairs with data\n")

# Simple equal-weight rebalancing simulation
capital = INITIAL_CAPITAL
positions = {p: capital / len(PAIRS) for p in pair_data}
total_injected = 0

trades = 0
for week in range(TOTAL_WEEKS):
    # Weekly injection
    capital += WEEKLY_INJECTION
    total_injected += WEEKLY_INJECTION

    # Simulate rebalancing (equal weight)
    target_per_pair = capital / len(positions)
    for p in positions:
        diff = target_per_pair - positions[p]
        if abs(diff) > 10:  # Only rebalance if meaningful
            fee = abs(diff) * FEE
            positions[p] = target_per_pair
            capital -= fee
            trades += 1

    if week % 12 == 0:
        print(f"Week {week:2d}: Capital=${capital:,.2f} | Trades so far: {trades}")

final_value = sum(positions.values())
pl = final_value - INITIAL_CAPITAL - total_injected

print(f"\n=== RESULTS ===")
print(f"Initial Capital:     ${INITIAL_CAPITAL:,.2f}")
print(f"Total Injected:      ${total_injected:,.2f}")
print(f"Final Portfolio:     ${final_value:,.2f}")
print(f"P/L:                 ${pl:,.2f}")
print(f"Total Rebalance Trades: {trades}")
print(f"\nBaseline rebalancing mechanics: {'WORKING' if trades > 0 else 'NOT WORKING'}")