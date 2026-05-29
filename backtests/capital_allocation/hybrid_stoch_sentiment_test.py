#!/usr/bin/env python3
"""
Hybrid: Stochastic RSI + Sentiment Filter Test
"""

import json
import os
import numpy as np

DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
PAIRS = ["btc", "eth", "sol", "xrp", "doge"]

INITIAL_CAPITAL = 10000.0
WEEKLY_INJECTION = 100.0
TOTAL_WEEKS = 52
FEE = 0.005
REBALANCE_INTERVAL = 7
SENTIMENT_THRESHOLD = 0.25

def load_ohlcv(pair):
    fname = f"backtest_historical_ohlcv_{pair}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    return filtered

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        upval = delta if delta > 0 else 0.
        downval = -delta if delta < 0 else 0.
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def calculate_stoch_rsi(prices, period=14):
    rsi = calculate_rsi(prices, period)
    stoch_rsi = np.zeros_like(rsi)
    for i in range(period, len(rsi)):
        rsi_window = rsi[i-period:i+1]
        min_rsi = np.min(rsi_window)
        max_rsi = np.max(rsi_window)
        if max_rsi - min_rsi > 0:
            stoch_rsi[i] = (rsi[i] - min_rsi) / (max_rsi - min_rsi) * 100
        else:
            stoch_rsi[i] = 50
    return stoch_rsi

def simulate_sentiment(week):
    # Simple simulated sentiment (same as main backtest)
    base = 0.20 + (week % 12) * 0.02
    return min(max(base, 0.0), 1.0)

print("=== HYBRID: Stochastic RSI + Sentiment Filter ===\n")

pair_data = {p: load_ohlcv(p) for p in PAIRS}

capital = INITIAL_CAPITAL
positions = {p: capital / len(PAIRS) for p in PAIRS}
total_injected = 0
trades = 0

for week in range(TOTAL_WEEKS):
    capital += WEEKLY_INJECTION
    total_injected += WEEKLY_INJECTION

    if week % REBALANCE_INTERVAL == 0:
        sentiment = simulate_sentiment(week)
        
        for p in PAIRS:
            prices = [float(d['close']) for d in pair_data[p][:week*7+7]]
            if len(prices) < 25:
                continue

            stoch = calculate_stoch_rsi(prices)
            stoch_signal = stoch[-1] < 25  # Slightly relaxed

            # Hybrid rule: Stochastic RSI + sentiment confirmation
            if stoch_signal and sentiment >= SENTIMENT_THRESHOLD:
                target = capital / len(PAIRS)
                diff = target - positions[p]
                if abs(diff) > 10:
                    fee = abs(diff) * FEE
                    positions[p] = target
                    capital -= fee
                    trades += 1

final_value = sum(positions.values())
pl = final_value - INITIAL_CAPITAL - total_injected

print(f"Trades: {trades}")
print(f"Final Value: ${final_value:,.2f}")
print(f"P/L: ${pl:,.2f} ({(pl/(INITIAL_CAPITAL+total_injected))*100:.1f}%)")