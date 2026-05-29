#!/usr/bin/env python3
"""
Combined Strategy with 30-min inspired parameters on Daily data
- RSI length: 14 (within 9-14 range)
- Other parameters kept strict
"""

import json
import os
import pandas as pd
import numpy as np

DATA_DIR = "/home/brad/.openclaw/workspace/coding-products/crypto-bot"
PAIRS = ["btc", "eth", "sol", "xrp", "doge"]

INITIAL_CAPITAL = 10000.0
WEEKLY_INJECTION = 100.0
TOTAL_WEEKS = 52
FEE = 0.004

def load_ohlcv(pair):
    fname = f"backtest_historical_ohlcv_{pair}_2025-04-20_to_2026-04-20.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        data = json.load(f)
    filtered = [d for d in data if d['timestamp'] >= '2025-05-05T00:00:00Z']
    df = pd.DataFrame(filtered)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')
    df = df.resample('D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna()
    return df

def add_indicators(df, rsi_length=14):
    # RSI (using suggested 9-14 range)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_length).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * (df['close'] - low14) / (high14 - low14)

    # Bollinger Bands
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_lower'] = sma20 - (std20 * 2)
    df['bb_upper'] = sma20 + (std20 * 2)
    return df

print("=== Combined Strategy (30-min params on Daily data) ===\n")

pair_data = {}
for p in PAIRS:
    df = load_ohlcv(p)
    df = add_indicators(df, rsi_length=14)
    pair_data[p] = df
    print(f"Loaded {p}: {len(df)} bars")

capital = INITIAL_CAPITAL
positions = {p: 0.0 for p in PAIRS}
total_injected = 0
trades = 0

for week in range(TOTAL_WEEKS):
    capital += WEEKLY_INJECTION
    total_injected += WEEKLY_INJECTION

    for p in PAIRS:
        df = pair_data[p]
        if len(df) <= week:
            continue

        row = df.iloc[week]
        prev = df.iloc[week-1] if week > 0 else row

        # Buy
        macd_bull = row['macd'] > prev['macd']
        rsi_os = row['rsi'] < 30
        stoch_os = row['stoch_k'] < 20
        lower_bb = row['close'] <= row['bb_lower']

        buy = macd_bull and rsi_os and stoch_os and lower_bb

        # Balanced Sell
        rsi_ob = row['rsi'] > 70
        macd_bear = row['macd'] < prev['macd']
        upper_bb = row['close'] > row['bb_upper']
        sell = rsi_ob or macd_bear or upper_bb

        if buy and positions[p] == 0:
            alloc = capital * 0.2
            positions[p] = alloc * (1 - FEE)
            capital -= alloc
            trades += 1
        elif sell and positions[p] > 0:
            capital += positions[p] * (1 - FEE)
            positions[p] = 0
            trades += 1

    if week % 12 == 0:
        val = capital + sum(positions.values())
        print(f"Week {week}: ${val:,.2f} | Trades={trades}")

final = capital + sum(positions.values())
pl = final - INITIAL_CAPITAL - total_injected
print(f"\nFinal: ${final:,.2f} | P/L: ${pl:,.2f} ({pl/(INITIAL_CAPITAL+total_injected)*100:.1f}%) | Trades: {trades}")