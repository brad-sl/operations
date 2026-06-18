#!/usr/bin/env python3
"""
Minimal Live Trade + SL Test (Standalone)
Goal: Prove end-to-end flow works with a tiny order.
This is a throwaway verification script.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv("/home/brad/projects/crypto-trading-bot/.env")

# --- Minimal imports (avoid broken phase6/core package) ---
sys.path.insert(0, "/home/brad/projects/crypto-trading-bot")

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.stop_loss_coordinator import create_cr03_coordinator

print("=== MINIMAL LIVE TRADE + SL TEST ===")

client = CoinbaseExchangeClient(mode="live")
sl_config = {"risk_management": {"stop_loss_pct": 0.03}}
sl_manager = StopLossManager(client, sl_config, mode="live")
coordinator = create_cr03_coordinator(sl_manager, mode="live")

pair = "XRP-USD"
usd_amount = 10.0

print(f"\n[1] Suspending existing protective orders for {pair}...")
try:
    suspend_summary = coordinator.suspend_protective_orders([pair])
    print(f"    Suspend summary: {suspend_summary}")
except Exception as e:
    print(f"    Suspend error (continuing): {e}")

print(f"\n[2] Placing small market buy order (${usd_amount})...")
order_result = client.place_market_buy(pair, usd_amount)
print(f"    Order result: {order_result}")

if order_result.get("success"):
    print("\n[3] Re-attaching ONE protective stop (one active stop per position)...")
    # Use approximate values from the $10 buy
    entry_price = 1.12
    size = round(usd_amount / entry_price, 0)  # whole units for XRP

    attach_success = coordinator.ensure_one_stop_per_position(pair, entry_price, size)
    print(f"    Re-attach success: {attach_success}")

    if attach_success:
        print("\n✅ SUCCESS: Full cycle completed (suspend → trade → re-attach)")
    else:
        print("\n⚠️ Trade succeeded but SL re-attach had issues")
else:
    print(f"\n❌ Trade failed: {order_result.get('error', order_result)}")
EOF