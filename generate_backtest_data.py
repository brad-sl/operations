#!/usr/bin/env python3
"""Generate synthetic historical OHLCV data for Phase 6 backtesting."""
import json
from datetime import datetime, timedelta
import numpy as np

def generate_ohlcv_data(ticker: str, start_price: float, days: int = 365, seed: int = 42):
    """Generate synthetic realistic OHLCV candles."""
    np.random.seed(seed)
    
    candles = []
    current_date = datetime(2025, 4, 20)
    current_price = start_price
    
    for day in range(days):
        # Generate realistic daily volatility (2-3%)
        daily_return = np.random.normal(0.0005, 0.02)  # mean +0.05%, std 2%
        open_price = current_price
        
        # High/Low based on intraday volatility
        high = open_price * (1 + abs(np.random.normal(0, 0.015)))
        low = open_price * (1 - abs(np.random.normal(0, 0.015)))
        close = open_price * (1 + daily_return)
        
        # Volume (billions for major pairs)
        volume = np.random.uniform(1e9, 5e9) if ticker in ['BTC', 'ETH'] else np.random.uniform(1e8, 1e9)
        
        candles.append({
            "timestamp": current_date.isoformat() + "Z",
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": int(volume)
        })
        
        current_price = close
        current_date += timedelta(days=1)
    
    return candles

# Generate data for all pairs
pairs = {
    'BTC': 63500.0,
    'ETH': 2300.0,
    'SOL': 140.0,
    'XRP': 2.50,
    'DOGE': 0.45
}

print("Generating synthetic historical OHLCV data...")
for ticker, start_price in pairs.items():
    candles = generate_ohlcv_data(ticker, start_price, days=365)
    filename = f'/home/brad/.openclaw/workspace/operations/crypto-bot/backtest_historical_ohlcv_{ticker.lower()}_2025-04-20_to_2026-04-20.json'
    
    with open(filename, 'w') as f:
        json.dump(candles, f, indent=2)
    
    print(f"✅ Generated {filename} ({len(candles)} candles)")

print("\n✅ All historical data generated successfully!")
