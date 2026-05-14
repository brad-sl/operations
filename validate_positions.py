#!/usr/bin/env python3
"""
Position Validator: Compares expected holdings vs. actual Coinbase wallet
Detects silent order failures and reconciliation gaps
"""

import json
import sys
import os
from dotenv import load_dotenv
from coinbase_wrapper import CoinbaseWrapper

load_dotenv()

# Expected holdings from Phase 5.1 execution (Apr 20, 16:29 PT)
EXPECTED_HOLDINGS = {
    "BTC-USD": {"qty": 0.00257185, "order_id": "aca8e907-cf42-415e-a627-83fcbd15bb86"},
    "ETH-USD": {"qty": 0.04984393, "order_id": "3cad68df-e5c6-41b0-a5b7-55b83acdd6d2"},
    "SOL-USD": {"qty": 1.41893932, "order_id": "57654ee1-1542-4484-bb89-877202086f18"},
    "XRP-USD": {"qty": 43.36797600, "order_id": "d7c4cfb2-633e-4567-9db7-a8728c5d1977"},
    "DOGE-USD": {"qty": 654.10000000, "order_id": "0778cb10-0cdc-4fd0-b4e9-d36a007beabc"},
}

def validate_positions():
    print("=" * 80)
    print("POSITION VALIDATION: Phase 5.1 Holdings Check")
    print("=" * 80)
    
    try:
        api_key = os.getenv("COINBASE_API_KEY")
        private_key = os.getenv("COINBASE_PRIVATE_KEY")
        
        if not api_key or not private_key:
            print("❌ ERROR: COINBASE_API_KEY or COINBASE_PRIVATE_KEY not set")
            return False
        
        cb = CoinbaseWrapper(api_key, private_key)
        print("✅ Connected to Coinbase API\n")
        
        mismatches = []
        total_discrepancy = 0
        
        for pair, expected in EXPECTED_HOLDINGS.items():
            base_asset = pair.split("-")[0]
            
            # Get actual balance
            balance = cb.get_account_balance(base_asset)
            actual_qty = float(balance.get("available", 0))
            expected_qty = expected["qty"]
            
            # Calculate discrepancy
            diff = actual_qty - expected_qty
            pct_diff = (diff / expected_qty * 100) if expected_qty > 0 else 0
            
            status = "✅ MATCH" if abs(diff) < 0.0001 else "❌ MISMATCH"
            
            print(f"{pair}:")
            print(f"  Expected: {expected_qty:.8f}")
            print(f"  Actual:   {actual_qty:.8f}")
            print(f"  Diff:     {diff:+.8f} ({pct_diff:+.2f}%)")
            print(f"  Status:   {status}")
            print(f"  Order ID: {expected['order_id']}\n")
            
            if abs(diff) > 0.0001:
                mismatches.append({
                    "pair": pair,
                    "expected": expected_qty,
                    "actual": actual_qty,
                    "diff": diff,
                    "order_id": expected["order_id"]
                })
                total_discrepancy += abs(diff)
        
        # Summary
        print("=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        
        if mismatches:
            print(f"❌ CRITICAL: {len(mismatches)} HOLDINGS MISMATCH(ES) DETECTED\n")
            for m in mismatches:
                print(f"  • {m['pair']}: Expected {m['expected']:.8f}, got {m['actual']:.8f}")
                print(f"    → Order: {m['order_id']}")
                print(f"    → Diff: {m['diff']:+.8f}\n")
            
            print(f"Total discrepancy value: {total_discrepancy:.8f} units")
            print("\n⚠️  ACTION REQUIRED:")
            print("  1. Check Coinbase order status for failed orders")
            print("  2. Verify all 5 orders are FILLED (not PENDING/CANCELLED)")
            print("  3. Retry failed pairs")
            return False
        else:
            print("✅ ALL HOLDINGS MATCH EXPECTED ALLOCATION")
            print("   Phase 5.1 trading capital is correctly deployed.")
            return True
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print("\n⚠️  Cannot validate: Check API connection and credentials")
        return False

if __name__ == "__main__":
    success = validate_positions()
    sys.exit(0 if success else 1)
