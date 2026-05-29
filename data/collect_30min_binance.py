#!/usr/bin/env python3
"""
30-Minute OHLCV Collector using Binance Public API (with better headers)
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ================== CONFIG ==================
PAIRS = {
    "BTCUSDT": "btc",
    "ETHUSDT": "eth",
    "SOLUSDT": "sol",
    "XRPUSDT": "xrp",
    "DOGEUSDT": "doge",
}

INTERVAL = "30m"
DAYS_BACK = 400
LIMIT = 1000

OUTPUT_DIR = Path("/home/brad/projects/crypto-trading-bot/data/30min")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
# ============================================


def fetch_klines(symbol: str, start_time: int, end_time: int):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "startTime": start_time,
        "endTime": end_time,
        "limit": LIMIT,
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def collect_binance(symbol: str, days: int = DAYS_BACK) -> pd.DataFrame:
    print(f"Collecting {symbol} 30m data from Binance...")
    end_time = int(time.time() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    all_klines = []
    current_start = start_time

    while current_start < end_time:
        try:
            data = fetch_klines(symbol, current_start, end_time)
            if not data:
                break
            all_klines.extend(data)
            current_start = data[-1][0] + 1
            time.sleep(1.2)  # More polite delay
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
            break

    if not all_klines:
        return pd.DataFrame()

    df = pd.DataFrame(all_klines, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].astype(float)
    df = df.set_index("timestamp")
    return df


def save_parquet(df: pd.DataFrame, pair: str):
    filename = OUTPUT_DIR / f"{pair}_30m.parquet"
    df.to_parquet(filename, compression="zstd")
    print(f"  Saved {len(df)} rows → {filename}")


if __name__ == "__main__":
    for binance_symbol, short_name in PAIRS.items():
        try:
            df = collect_binance(binance_symbol)
            if not df.empty:
                save_parquet(df, short_name)
        except Exception as e:
            print(f"Failed {binance_symbol}: {e}")

    print("\nDone.")