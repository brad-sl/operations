#!/usr/bin/env python3
"""
Minimal isolated test: Can we fetch even ONE historical candle?
Start simple. Verify before adding complexity.
"""

from dotenv import load_dotenv
load_dotenv()

from phase6.core.exchange_client import CoinbaseExchangeClient
from datetime import datetime, timedelta, timezone

def main():
    print("=== Minimal Historical Price Test ===\n")

    client = CoinbaseExchangeClient(mode="live")

    product_id = "BTC-USD"

    # Simplest possible test: try to get the last 1 hour candle
    print(f"Attempting to fetch 1 recent candle for {product_id}...")

    try:
        # Use the method we added
        prices = client.get_recent_prices(product_id, limit=1, granularity="ONE_HOUR")
        print(f"Result: {prices}")
        print(f"Count: {len(prices)}")

        if prices:
            print("\n✅ SUCCESS: Got at least one historical price")
        else:
            print("\n❌ No prices returned")

    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    main()
