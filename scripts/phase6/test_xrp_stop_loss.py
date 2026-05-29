#!/usr/bin/env python3
"""
Test script: Verify and attach Stop Loss on the current live XRP position.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.exchange_client import CoinbaseExchangeClient

def main():
    print("=" * 60)
    print("LIVE STOP LOSS TEST - XRP Position")
    print("=" * 60)

    # Initialize live client
    client = CoinbaseExchangeClient(mode="live")
    sl_manager = StopLossManager(client, {"risk_management": {"stop_loss_pct": 0.03}}, mode="live")

    pair = "XRP-USD"

    # Check if SL already exists
    print(f"\n[1] Checking for existing stop loss on {pair}...")
    has_sl = sl_manager.has_active_stop_loss(pair)
    print(f"    Existing stop loss found: {has_sl}")

    if has_sl:
        print("\n[RESULT] Stop loss already active on XRP. No action needed.")
        return

    # Get current price as proxy for entry price
    print(f"\n[2] Getting current price for {pair}...")
    price = client.get_price(pair)
    print(f"    Current price: ${price}")

    if price <= 0:
        print("[ERROR] Could not get valid price. Aborting.")
        return

    # Attach stop loss (using 3% default)
    print(f"\n[3] Attaching 3% stop loss to {pair}...")
    success = sl_manager.attach_stop_loss(pair, price, sl_pct=0.03)

    if success:
        print(f"\n[SUCCESS] Stop loss attached for {pair}")
    else:
        print(f"\n[FAIL] Could not attach stop loss for {pair}")

if __name__ == "__main__":
    main()
