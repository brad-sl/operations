#!/usr/bin/env python3
"""Diagnostic script to inspect raw Coinbase get_accounts() response."""

import os
import json
from coinbase_wrapper_FIXED import CoinbaseWrapper

def main():
    api_key = os.getenv("COINBASE_API_KEY")
    private_key = os.getenv("COINBASE_API_SECRET")

    if not api_key or not private_key:
        print("ERROR: COINBASE_API_KEY and COINBASE_API_SECRET must be set")
        return

    private_key = private_key.replace("\\n", "\n")

    client = CoinbaseWrapper(api_key=api_key, private_key=private_key, sandbox=False)
    print("✅ Client initialized")

    accounts = client.get_accounts()
    print("\n=== RAW RESPONSE (first 3 accounts) ===")
    for i, acc in enumerate(accounts.get("accounts", [])[:3]):
        print(f"\nAccount {i}:")
        print(json.dumps(acc, indent=2))

    print("\n=== CRYPTO HOLDINGS DETECTED ===")
    for acc in accounts.get("accounts", []):
        currency = acc.get("currency", "")
        if currency in ("USD", "USDC"):
            continue
        ab = acc.get("available_balance") or acc.get("balance") or {}
        val = ab.get("value") if isinstance(ab, dict) else None
        print(f"{currency}: available_balance.value = {val}")

if __name__ == "__main__":
    main()