#!/usr/bin/env python3
"""
Portfolio-Level Combined Strategy Test (Daily)
Indicators calculated manually (no pandas_ta dependency)
"""

import json
import os
import numpy as np
import pandas as pd

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

def add_indicators(df):
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
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

print("=== Combined MACD + RSI + Stoch + BB Portfolio Test (Daily) ===\n")

pair_data = {}
for p in PAIRS:
    try:
        df = load_ohlcv(p)
        df = add_indicators(df)
        pair_data[p] = df
        print(f"Loaded {p}: {len(df)} daily bars")
    except Exception as e:
        print(f"Failed {p}: {e}")

print()

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

        # Buy conditions
        macd_bullish = row['macd'] > prev['macd']
        rsi_oversold = row['rsi'] < 30
        stoch_oversold = row['stoch_k'] < 20
        at_lower_band = row['close'] <= row['bb_lower']

        buy_signal = macd_bullish and rsi_oversold and stoch_oversold and at_lower_band

        # Balanced Sell conditions
        rsi_overbought = row['rsi'] > 70
        macd_bearish = row['macd'] < prev['macd']
        above_upper_band = row['close'] > row['bb_upper']

        sell_signal = rsi_overbought or macd_bearish or above_upper_band

        # Execute trades
        if buy_signal and positions[p] == 0:
            allocation = capital * 0.2
            fee = allocation * FEE
            positions[p] = allocation - fee
            capital -= allocation
            trades += 1

        elif sell_signal and positions[p] > 0:
            capital += positions[p] * (1 - FEE)
            positions[p] = 0
            trades += 1

    if week % 12 == 0:
        total_value = capital + sum(positions.values())
        print(f"Week {week:2d}: Portfolio=${total_value:,.2f} | Trades={trades}")

final_value = capital + sum(positions.values())
pl = final_value - INITIAL_CAPITAL - total_injected

print(f"\n=== FINAL RESULTS ===")
print(f"Final Portfolio Value: ${final_value:,.2f}")
print(f"Total P/L: ${pl:,.2f} ({(pl / (INITIAL_CAPITAL + total_injected)) * 100:.1f}%)")
print(f"Total Trades: {trades}")