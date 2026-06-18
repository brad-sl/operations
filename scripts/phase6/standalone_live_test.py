#!/usr/bin/env python3
"""
Standalone Live Trade + SL Test
Completely self-contained.
"""

import os
import sys
import secrets
from dotenv import load_dotenv

# Ensure we can find the wrapper
sys.path.insert(0, "/home/brad/projects/crypto-trading-bot")
load_dotenv("/home/brad/projects/crypto-trading-bot/.env")

from coinbase_wrapper_FIXED import CoinbaseWrapper

print("=== STANDALONE LIVE TRADE + SL TEST ===")

api_key = os.getenv("COINBASE_API_KEY")
private_key = os.getenv("COINBASE_API_SECRET")

wrapper = CoinbaseWrapper(api_key=api_key, private_key=private_key)
print("CoinbaseWrapper initialized")

pair = "XRP-USD"
usd_amount = 10.0

print(f"\n[1] Suspending existing stops for {pair}...")
try:
    resp = wrapper._request("GET", "/api/v3/brokerage/orders/historical/batch", 
                            {"order_status": "OPEN", "product_id": pair})
    orders = resp.get("orders", []) if isinstance(resp, dict) else []
    stop_orders = [o for o in orders if "stop" in str(o.get("order_type", "")).lower()]
    for order in stop_orders:
        oid = order.get("order_id")
        if oid:
            wrapper._request("POST", f"/api/v3/brokerage/orders/{oid}/cancel", {})
            print(f"    Cancelled: {oid}")
except Exception as e:
    print(f"    (continuing) {e}")

print(f"\n[2] Placing market buy: ${usd_amount} {pair}...")
body = {
    "client_order_id": secrets.token_hex(16),
    "product_id": pair,
    "side": "BUY",
    "order_configuration": {
        "market_market_ioc": {"quote_size": str(usd_amount)}
    }
}
try:
    resp = wrapper._request("POST", "/api/v3/brokerage/orders", body)
    if "success_response" in resp or resp.get("success"):
        oid = resp.get("success_response", {}).get("order_id")
        print(f"    ✅ Trade successful! Order ID: {oid}")
        trade_success = True
    else:
        print(f"    ❌ Failed: {resp}")
        trade_success = False
except Exception as e:
    print(f"    ❌ Exception: {e}")
    trade_success = False

if trade_success:
    print(f"\n[3] Re-attaching single stop...")
    entry_price = 1.12
    size = 8.9
    stop_price = round(entry_price * 0.97, 2)
    limit_price = round(stop_price * 0.995, 2)

    stop_body = {
        "client_order_id": secrets.token_hex(16),
        "product_id": pair,
        "side": "SELL",
        "order_configuration": {
            "stop_limit_stop_limit_gtc": {
                "base_size": str(int(size)),
                "limit_price": str(limit_price),
                "stop_price": str(stop_price)
            }
        }
    }
    try:
        stop_resp = wrapper._request("POST", "/api/v3/brokerage/orders", stop_body)
        if "success_response" in stop_resp or stop_resp.get("success"):
            print("    ✅ Stop attached")
            print("\n✅ FULL CYCLE SUCCESS")
        else:
            print(f"    ⚠️ Stop response: {stop_resp}")
    except Exception as e:
        print(f"    ⚠️ Stop error: {e}")
else:
    print("\n❌ Skipping stop re-attach")
