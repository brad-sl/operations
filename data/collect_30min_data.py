#!/usr/bin/env python3
"""
30-Minute OHLCV Data Collector for Phase 6
Uses Finnhub (recommended)

Storage: Parquet (much more compact than JSON)

How to get a free Finnhub API key:
1. Go to https://finnhub.io/
2. Click "Get free API key"
3. Sign up with email (no credit card required)
4. Copy your API key from the dashboard
5. Set it as environment variable: export FINNHUB_API_KEY="your_key"
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ================== CONFIG ==================
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
RESOLUTION = "30"
DAYS_BACK = 400

OUTPUT_DIR = Path("/home/brad/projects/crypto-trading-bot/data/30min")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
# ============================================


def collect_finnhub(pair: str, days: int = DAYS_BACK) -> pd.DataFrame:
    """Collect 30-min data from Finnhub (tries multiple symbol formats)"""
    if not FINNHUB_API_KEY:
        raise ValueError("FINNHUB_API_KEY environment variable not set")

    import requests

    end = int(time.time())
    start = int((datetime.now() - timedelta(days=days)).timestamp())

    # Try both common symbol formats
    for symbol in [pair, f"BINANCE:{pair}"]:
        url = "https://finnhub.io/api/v1/crypto/candle"
        params = {
            "symbol": symbol,
            "resolution": RESOLUTION,
            "from": start,
            "to": end,
            "token": FINNHUB_API_KEY,
        }

        print(f"  Trying symbol={symbol} ...")
        resp = requests.get(url, params=params, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("s") == "ok":
                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(data["t"], unit="s"),
                    "open": data["o"],
                    "high": data["h"],
                    "low": data["l"],
                    "close": data["c"],
                    "volume": data["v"],
                })
                df = df.set_index("timestamp")
                return df
            else:
                print(f"    Finnhub response: {data.get('s')}")
        else:
            print(f"    HTTP {resp.status_code}")

    print(f"  All attempts failed for {pair}")
    return pd.DataFrame()


def save_parquet(df: pd.DataFrame, pair: str):
    filename = OUTPUT_DIR / f"{pair.lower()}_30m.parquet"
    df.to_parquet(filename, compression="zstd")
    print(f"  Saved {len(df)} rows → {filename}")


if __name__ == "__main__":
    if not FINNHUB_API_KEY:
        print("ERROR: FINNHUB_API_KEY not set.")
        print("Get a free key at https://finnhub.io/ and export it.")
        exit(1)

    for pair in PAIRS:
        try:
            df = collect_finnhub(pair)
            if not df.empty:
                save_parquet(df, pair)
            time.sleep(2)  # Respect free tier
        except Exception as e:
            print(f"Failed to collect {pair}: {e}")

    print("\nDone.")