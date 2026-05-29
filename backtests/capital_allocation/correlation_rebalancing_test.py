#!/usr/bin/env python3
"""
Correlation-Based Rebalancing Test (Phase 6 logic)
Goal: Test whether correlation-aware rebalancing improves ROI over simple equal-weight.
"""

import json
import os
import numpy as np
from collections import defaultdict

DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
PAIRS = ["btc", "eth", "sol", "xrp", "doge"]

INITIAL_CAPITAL = 10000.0
WEEKLY_INJECTION = 100.0
TOTAL_WEEKS = 52
FEE = 0.003  # 0.3%
REBALANCE_INTERVAL = 7
CORR_WINDOW = 30  # 30-day window for correlation
HIGH_CORR_THRESHOLD = 0.70

def load_ohlcv(pair):
    fname = f"backtest_historical_ohlcv_{pair}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    return filtered

def get_price_series(data, weeks):
    """Get weekly closing prices"""
    prices = []
    for w in range(weeks):
        idx = min(w * 7, len(data) - 1)
        prices.append(float(data[idx]['close']))
    return prices

print("=== CORRELATION-BASED REBALANCING TEST ===\n")

pair_data = {p: load_ohlcv(p) for p in PAIRS}
price_history = {p: get_price_series(pair_data[p], TOTAL_WEEKS) for p in PAIRS}

capital = INITIAL_CAPITAL
positions = {p: capital / len(PAIRS) for p in PAIRS}
total_injected = 0
trades = 0
high_corr_weeks = 0

for week in range(TOTAL_WEEKS):
    capital += WEEKLY_INJECTION
    total_injected += WEEKLY_INJECTION

    if week >= CORR_WINDOW and week % REBALANCE_INTERVAL == 0:
        # Build price matrix for correlation
        matrix = []
        for p in PAIRS:
            start = max(0, week - CORR_WINDOW)
            matrix.append(price_history[p][start:week])
        
        if len(matrix[0]) >= 10:  # Need enough data
            corr_matrix = np.corrcoef(matrix)
            avg_corr = np.mean(corr_matrix[np.triu_indices_from(corr_matrix, k=1)])
            
            if avg_corr > HIGH_CORR_THRESHOLD:
                high_corr_weeks += 1
                # Reduce allocation to all pairs proportionally (simple version)
                # In real version this would identify clusters and reduce
                target = capital * 0.85 / len(PAIRS)  # Hold 15% in reserve during high corr
                for p in positions:
                    diff = target - positions[p]
                    if abs(diff) > 5:
                        fee = abs(diff) * FEE
                        positions[p] = target
                        capital -= fee
                        trades += 1
            else:
                # Normal equal-weight rebalance
                target = capital / len(PAIRS)
                for p in positions:
                    diff = target - positions[p]
                    if abs(diff) > 5:
                        fee = abs(diff) * FEE
                        positions[p] = target
                        capital -= fee
                        trades += 1

    if week % 12 == 0:
        print(f"Week {week:2d}: ${capital:,.2f} | Trades: {trades} | High-corr weeks: {high_corr_weeks}")

final_value = sum(positions.values())
pl = final_value - INITIAL_CAPITAL - total_injected
return_pct = (pl / (INITIAL_CAPITAL + total_injected)) * 100

print(f"\n=== RESULTS ===")
print(f"Final Value: ${final_value:,.2f}")
print(f"P/L: ${pl:,.2f} ({return_pct:.1f}%)")
print(f"Total Trades: {trades}")
print(f"Weeks in High-Correlation Regime: {high_corr_weeks}")