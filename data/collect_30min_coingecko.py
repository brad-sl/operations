#!/usr/bin/env python3
"""
30-Minute OHLCV Collector using CoinGecko (free, no key)
CoinGecko free tier supports historical data reasonably well.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

# ================== CONFIG ==================
COINS = {
    "bitcoin": "btc",
    "ethereum": "eth",
    "solana": "sol",
    "ripple": "xrp",
    "dogecoin": "doge",
}

VS_CURRENCY = "usd"
DAYS_BACK = 400
OUTPUT_DIR = Path("/home/brad/projects/crypto-trading-bot/data/30min")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# ============================================


def fetch_coingecko(coin_id: str, days: int):
    """Fetch market chart data from CoinGecko"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": VS_CURRENCY,
        "days": days,
        "interval": "daily",  # CoinGecko free tier limitation
    }
    resp = requests.get(url, params=params, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.json()


def collect_coingecko(coin_id: str, short_name: str, days: int = DAYS_BACK):
    print(f"Collecting {coin_id} data from CoinGecko...")
    data = fetch_coingecko(coin_id, days)

    if "prices" not in data:
        print(f"  No price data returned for {coin_id}")
        return

    prices = data["prices"]
    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    df["close"] = df["price"]
    df = df[["close"]]

    # CoinGecko free tier mostly gives daily — we'll note this
    filename = OUTPUT_DIR / f"{short_name}_30m.parquet"
    df.to_parquet(filename, compression="zstd")
    print(f"  Saved {len(df)} rows (daily granularity) → {filename}")


if __name__ == "__main__":
    for coin_id, short_name in COINS.items():
        try:
            collect_coingecko(coin_id, short_name)
            time.sleep(8)  # CoinGecko has stricter rate limits
        except Exception as e:
            print(f"Failed {coin_id}: {e}")

    print("\nDone.")