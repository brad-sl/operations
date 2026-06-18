#!/usr/bin/env python3
"""
Lightweight manual test wrapper for Coinbase holdings fetch.

Run this directly to debug get_holdings() / get_enriched_positions()
without going through the full runner.

Usage:
    python test_holdings_fetch.py
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

from phase6.core.exchange_client import CoinbaseExchangeClient


def main():
    print("=== Holdings Fetch Test Wrapper ===\n")

    # Initialize live client
    try:
        client = CoinbaseExchangeClient(mode="live")
        print("✅ Live client initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize live client: {e}")
        return

    # Test 1: Raw get_holdings()
    print("--- Test 1: get_holdings() ---")
    try:
        holdings = client.get_holdings()
        print(f"Raw holdings dict: {holdings}")
        print(f"Number of crypto assets with balance > 0: {len(holdings)}\n")
    except Exception as e:
        print(f"❌ get_holdings() failed: {e}\n")
        holdings = {}

    # Test 2: get_enriched_positions()
    print("--- Test 2: get_enriched_positions() ---")
    try:
        enriched = client.get_enriched_positions()
        print(json.dumps(enriched, indent=2))
        total_value = sum(p.get("value_usd", 0) for p in enriched.values())
        print(f"\nTotal holdings value (USD): ${total_value:,.2f}\n")
    except Exception as e:
        print(f"❌ get_enriched_positions() failed: {e}\n")

    # Test 3: Direct raw accounts inspection (for debugging)
    print("--- Test 3: Raw accounts sample (first 5 crypto) ---")
    try:
        accounts = client.real_client.get_accounts()
        crypto_accounts = [a for a in accounts.get("accounts", []) 
                          if a.get("currency") not in ("USD", "USDC")]
        for acc in crypto_accounts[:5]:
            print(f"{acc.get('currency')}: available_balance={acc.get('available_balance')}, hold={acc.get('hold')}")
    except Exception as e:
        print(f"❌ Raw accounts fetch failed: {e}")

    print("\n=== Test complete ===")


if __name__ == "__main__":
    main()