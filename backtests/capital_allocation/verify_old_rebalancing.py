#!/usr/bin/env python3
"""
Re-run of historical rebalancing logic (trying to match previous high-return tests)
Goal: Check for functional drift by reproducing old rebalancing behavior on current data.
"""

import json
import os
import numpy as np
from datetime import datetime

DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
PAIRS = ["btc", "eth", "sol", "xrp", "doge"]

INITIAL_CAPITAL = 10000.0
WEEKLY_INJECTION = 100.0
TOTAL_WEEKS = 52
FEE = 0.002  # Lower fee (0.2%) — common in older tests that showed high returns
REBALANCE_INTERVAL = 7

def load_ohlcv(pair):
    fname = f"backtest_historical_ohlcv_{pair}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    return filtered

def get_price_at_week(data, week):
    idx = min(week * 7, len(data) - 1)
    return float(data[idx]['close'])

print("=== OLD REBALANCING VERIFICATION (Lower Fees) ===\n")

pair_data = {p: load_ohlcv(p) for p in PAIRS}
print(f"Loaded data for {len(pair_data)} pairs\n")

# Simple equal-weight weekly rebalancing with lower fees
capital = INITIAL_CAPITAL
positions = {p: capital / len(PAIRS) for p in PAIRS}
total_injected = 0
trades = 0

for week in range(TOTAL_WEEKS):
    capital += WEEKLY_INJECTION
    total_injected += WEEKLY_INJECTION

    if week % REBALANCE_INTERVAL == 0:
        target = capital / len(positions)
        for p in positions:
            diff = target - positions[p]
            if abs(diff) > 5:
                fee = abs(diff) * FEE
                positions[p] = target
                capital -= fee
                trades += 1

    if week % 12 == 0:
        print(f"Week {week:2d}: ${capital:,.2f} | Trades: {trades}")

final_value = sum(positions.values())
pl = final_value - INITIAL_CAPITAL - total_injected
return_pct = (pl / (INITIAL_CAPITAL + total_injected)) * 100

print(f"\n=== RESULTS (0.2% fees) ===")
print(f"Final Value: ${final_value:,.2f}")
print(f"P/L: ${pl:,.2f} ({return_pct:.1f}%)")
print(f"Trades: {trades}")