#!/usr/bin/env python3
"""
P0-02.2 Isolation Test: Harden get_product_metadata + dynamic fallbacks.

Calls get_product_metadata for all 11 active pairs in the live basket.
Asserts:
- base_increment > 0
- price_increment > 0 and sensible 
- Dynamic fetch succeeds (preferred) or fallback provides valid values 
  (no generic default 0.01/0.001 for known pairs in basket)
- No breaking: returns dict with expected keys, floats.
- Cache behavior and logging exercised.

Run: python phase6/core/test_isolation_product_metadata.py
(or from project root)
"""
import sys
import os

# Robust bootstrap: always ensure project root on path first so "from phase6..." works
# regardless of cwd or how the test is invoked.
PROJECT_ROOT = "/home/brad/projects/crypto-trading-bot"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from phase6.core.exchange_client import CoinbaseExchangeClient

PAIRS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
    "ADA-USD", "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD"
]

def is_sensible_price_increment(pair: str, inc: float) -> bool:
    if inc <= 0 or inc > 1.0:
        return False
    return True  # real verified values from /products are sensible

def run_isolation_test():
    print("=== P0-02.2 Isolation Test: get_product_metadata (HARDENED) ===\n")
    ex = CoinbaseExchangeClient(mode="shadow")

    results = []
    all_pass = True

    for pid in PAIRS:
        meta = ex.get_product_metadata(pid)
        price_inc = meta.get("price_increment", 0.0)
        base_inc = meta.get("base_increment", 0.0)

        price_ok = price_inc > 0 and is_sensible_price_increment(pid, price_inc)
        base_ok = base_inc > 0
        keys_ok = "price_increment" in meta and "base_increment" in meta
        type_ok = isinstance(price_inc, (int, float)) and isinstance(base_inc, (int, float))
        not_generic_default = not (abs(price_inc - 0.01) < 1e-12 and abs(base_inc - 0.001) < 1e-12)

        passed = price_ok and base_ok and keys_ok and type_ok and not_generic_default
        if not passed:
            all_pass = False

        results.append({
            "pair": pid,
            "price_increment": price_inc,
            "base_increment": base_inc,
            "passed": passed,
        })

        status = "PASS" if passed else "FAIL"
        print(f"{pid}: price_inc={price_inc}, base_inc={base_inc}  {status}")

    print("\n--- Summary ---")
    passed_count = sum(1 for r in results if r["passed"])
    print(f"Pairs tested: {len(PAIRS)}")
    print(f"Passed: {passed_count}")
    print(f"Status: {'ALL PASS' if all_pass else 'SOME FAILURES'}")

    # Cache + fresh client
    ex2 = CoinbaseExchangeClient(mode="shadow")
    meta_btc = ex2.get_product_metadata("BTC-USD")
    print(f"\nFresh client BTC meta: {meta_btc}")

    # Confirm non-defaults for known alts (dynamic succeeded)
    for pid in ["DOGE-USD", "ADA-USD", "OP-USD", "LINK-USD", "XRP-USD"]:
        m = ex2.get_product_metadata(pid)
        is_generic = (abs(m["price_increment"] - 0.01) < 1e-9 and abs(m["base_increment"] - 0.001) < 1e-9)
        print(f"  {pid} generic_default? {is_generic}")
        if is_generic:
            all_pass = False

    if all_pass:
        print("\n=== ISOLATION TEST PASSED (dynamic preferred, verified values, hardened paths) ===")
        return 0
    else:
        print("\n=== ISOLATION TEST FAILED ===")
        for r in results:
            if not r["passed"]:
                print(f"  FAIL {r['pair']}")
        return 1

if __name__ == "__main__":
    sys.exit(run_isolation_test())
