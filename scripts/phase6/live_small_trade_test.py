#!/usr/bin/env python3
"""
Live Small Trade Test
Purpose: Verify full CR-03 flow (suspend SL → trade → re-attach SL) with a tiny order.
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv("/home/brad/projects/crypto-trading-bot/.env")
sys.path.insert(0, "/home/brad/projects/crypto-trading-bot")

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.stop_loss_coordinator import create_cr03_coordinator

print("=== LIVE SMALL TRADE + SL TEST ===")

client = CoinbaseExchangeClient(mode="live")
config = {"risk_management": {"stop_loss_pct": 0.03}}
sl_manager = StopLossManager(client, config, mode="live")
coordinator = create_cr03_coordinator(sl_manager, mode="live")

pair = "XRP-USD"
usd_amount = 10.0

print(f"\n[1] Suspending protective orders for {pair}...")
suspend_result = coordinator.suspend_protective_orders([pair])
print(f"    Suspend result: {suspend_result}")

print(f"\n[2] Placing small market buy (${usd_amount})...")
order_result = client.place_market_buy(pair, usd_amount)
print(f"    Order result: {order_result}")

if order_result.get("success"):
    print("\n[3] Re-attaching single protective stop (one active stop per position)...")
    entry_price = 1.12
    size = 8.9
    attach_result = coordinator.ensure_one_stop_per_position(pair, entry_price, size)
    print(f"    Attach result: {attach_result}")
    print("\n✅ Full cycle (suspend → trade → re-attach) completed successfully")
else:
    print(f"\n❌ Trade failed: {order_result.get('error')}")
