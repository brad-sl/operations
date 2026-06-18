#!/usr/bin/env python3
"""
Minimal test: Try the public Coinbase endpoint (no auth)
"""

import requests
from datetime import datetime, timedelta, timezone

def main():
    print("=== Public Coinbase Candles Test ===\n")

    product_id = "BTC-USD"
    granularity = 3600  # 1 hour in seconds

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=3)

    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
    params = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": granularity
    }

    print(f"Requesting: {url}")
    print(f"Params: {params}\n")

    try:
        resp = requests.get(url, params=params, timeout=15)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"Received {len(data)} candles")
            if data:
                print(f"Most recent close: {data[0][4]}")
                print("\n✅ SUCCESS: Public endpoint works")
        else:
            print(f"Response: {resp.text[:300]}")
            print("\n❌ Failed")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    main()
