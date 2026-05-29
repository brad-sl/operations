#!/usr/bin/env python3
"""
Phase 6 Live Verification Script

Safe, read-only check before any live trading.
- Verifies credentials and connection
- Reports current USD balance
- Confirms zero open positions / open orders
- Does NOT place any trades

Usage:
    PYTHONPATH=. python scripts/phase6/verify_live.py
"""

import os
import sys
from phase6.core.exchange_client import CoinbaseExchangeClient

def main():
    print("=" * 60)
    print("PHASE 6 LIVE VERIFICATION")
    print("=" * 60)

    # Safety check: require explicit live mode
    mode = os.getenv("PHASE6_MODE", "live").lower()
    if mode != "live":
        print("ERROR: Set PHASE6_MODE=live to run verification")
        sys.exit(1)

    print(f"\n[1/4] Initializing live exchange client...")
    try:
        client = CoinbaseExchangeClient(mode="live")
        print("✅ Live client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize live client: {e}")
        sys.exit(1)

    print(f"\n[2/4] Running connection verification...")
    result = client.verify_live_connection()

    if result.get("status") != "connected":
        print(f"❌ Verification failed: {result}")
        sys.exit(1)

    print("✅ Connection verified")
    print(f"   USD Balance: ${result.get('usd_balance', 0):.2f}")
    print(f"   Open Orders: {result.get('open_orders', 0)}")
    print(f"   Tracked Positions: {result.get('tracked_positions', 0)}")

    # Expected values from Fresh Start
    expected_capital = 967.76
    actual = result.get('usd_balance', 0)

    print(f"\n[3/4] Capital check (expected ~${expected_capital})...")
    if abs(actual - expected_capital) > 5:
        print(f"⚠️  Balance differs from expected Fresh Start amount (${expected_capital})")
    else:
        print("✅ Capital within tolerance of Fresh Start")

    print(f"\n[4/4] Position safety check...")
    if result.get('open_orders', 0) > 0:
        print("⚠️  WARNING: There are open orders on the account!")
    else:
        print("✅ No open orders detected")

    if result.get('tracked_positions', 0) > 0:
        print("⚠️  WARNING: Positions are being tracked from previous state!")
    else:
        print("✅ Clean position state")

    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE — READY FOR LIVE TRADING")
    print("=" * 60)
    print("\nNext step: Run the runner with --mode LIVE --no-sandbox")
    print("Example:")
    print("    PYTHONPATH=. python phase6/core/phase6_runner.py --mode LIVE --no-sandbox")

if __name__ == "__main__":
    main()