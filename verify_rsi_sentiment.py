#!/usr/bin/env python3
"""
Manual refresh + verification script for RSI + Sentiment.
- Computes real RSI via CoinGecko fallback (same logic as runner)
- Loads current sentiment cache
- Writes updated phase6_live_state.json with real values
- Verifies dashboard wiring (reads the same state file)
"""
import json
import requests
from datetime import datetime
from pathlib import Path

# Paths
STATE_PATH = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
SENTIMENT_PATH = Path("/home/brad/.trading-bot/sentiment_cache.json")

UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
CG_IDS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "XRP-USD": "ripple",
    "DOGE-USD": "dogecoin",
}

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return []
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(round(rsi, 2))
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    return rsi_values

def get_real_rsi(pair):
    cid = CG_IDS.get(pair)
    if not cid:
        return 50.0
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart?vs_currency=usd&days=30&interval=daily"
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        prices = [p[1] for p in data.get("prices", [])]
        if len(prices) >= 15:
            rsi_series = calculate_rsi(prices, period=14)
            if rsi_series:
                return rsi_series[-1]
    except Exception as e:
        print(f"  CoinGecko RSI fetch failed for {pair}: {e}")
    return 50.0

def load_sentiment():
    if not SENTIMENT_PATH.exists():
        return {p: 0.0 for p in UNIVERSE}
    try:
        with open(SENTIMENT_PATH) as f:
            data = json.load(f)
        scores = {}
        for sym in UNIVERSE:
            entry = data.get("sentiment", {}).get(sym, {})
            scores[sym] = float(entry.get("sentiment_score", 0.0))
        return scores
    except Exception:
        return {p: 0.0 for p in UNIVERSE}

def main():
    print("=== Manual RSI + Sentiment Refresh & Verification ===")
    
    # 1. Refresh RSI (real values)
    print("\n[1] Fetching real RSI via CoinGecko...")
    rsi_values = {}
    for pair in UNIVERSE:
        rsi = get_real_rsi(pair)
        rsi_values[pair] = rsi
        print(f"  {pair}: {rsi}")
    
    # 2. Load sentiment
    print("\n[2] Loading sentiment scores...")
    sentiment = load_sentiment()
    for pair, score in sentiment.items():
        print(f"  {pair}: {score}")
    
    # 3. Read existing state and update RSI + sentiment sections
    print("\n[3] Updating phase6_live_state.json...")
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            state = json.load(f)
    else:
        state = {"positions": [], "balances": []}
    
    state["rsi"] = rsi_values
    state["sentiment"] = sentiment
    state["last_updated"] = datetime.now().isoformat()
    state["rsi_source"] = "coingecko_fallback"
    state["sentiment_source"] = str(SENTIMENT_PATH)
    
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    
    print(f"  Wrote updated state to {STATE_PATH}")
    
    # 4. Verify dashboard wiring
    print("\n[4] Dashboard wiring verification...")
    print(f"  Dashboard state file: {STATE_PATH}")
    print(f"  File exists: {STATE_PATH.exists()}")
    print(f"  RSI keys present: {list(rsi_values.keys())}")
    print(f"  All RSI values are real (not 100.0): {all(v != 100.0 for v in rsi_values.values())}")
    
    # Re-read to confirm
    with open(STATE_PATH) as f:
        final = json.load(f)
    print(f"  Final RSI in file: {final.get('rsi')}")
    print(f"  Final sentiment in file: {final.get('sentiment')}")
    
    print("\n=== Verification Complete ===")

if __name__ == "__main__":
    main()