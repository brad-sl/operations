#!/usr/bin/env python3
"""
Minimal Code Isolation Test — PATCH for P6-001 in exchange_client.get_enriched_positions.
This shows what a correct get_enriched_positions must return after the boundary fix.
"""

from phase6.core.exchange_client import CoinbaseExchangeClient

def main():
    print("=== Boundary Patch Isolation Test (post-fix expectation) ===")
    client = CoinbaseExchangeClient(mode="shadow", initial_capital=1000.0)
    # Force some shadow holdings (the exchange client shadow has _positions)
    # In real usage this would come from live get_holdings.
    client._positions = {"BTC": 0.00423, "ETH": 0.12, "DOGE": 850.0}

    # Call the REAL method (after the fix we will implement)
    enriched = client.get_enriched_positions()
    print("Current get_enriched_positions() output:")
    for k, v in enriched.items():
        print(f"  {k}: keys={list(v.keys())} amount={v.get('amount')} value_usd={v.get('value_usd')}")

    # The key contract the runner (and deploy_capital) must see:
    has_usd_keys = all(k.endswith("-USD") for k in enriched.keys())
    uses_value_usd = all("value_usd" in v and isinstance(v["value_usd"], (int, float)) for v in enriched.values())

    print(f"\nContract check:")
    print(f"  All keys end with -USD: {has_usd_keys}")
    print(f"  All entries have numeric value_usd: {uses_value_usd}")

    if has_usd_keys and uses_value_usd:
        print("\n✅ Post-fix contract satisfied.")
    else:
        print("\n❌ Still returning the buggy shape.")
        return False
    return True

if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
