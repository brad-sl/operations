#!/usr/bin/env python3
"""
Coinbase Advanced Trade API Diagnostic - Isolation Test Script
Goal: Test EVERY core trading function end-to-end with real data.
Run this to solidify the API layer.

Usage:
  python scripts/diagnose_coinbase_api.py --all
  python scripts/diagnose_coinbase_api.py --balance --holdings --orders --price --buy-test (small)

This is the canonical isolation test for fixing the flaky API layer.
"""

import sys
import os
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(PROJECT_ROOT))

# Force load env before any imports that use dotenv
from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"))
load_dotenv(str(Path.home() / ".hermes" / ".env"))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.order_executor import OrderExecutor

def test_balance(client):
    print("\n=== TEST: get_account_balance (USD) ===")
    try:
        bal = client.get_account_balance("USD")
        print(f"USD Balance: ${bal:.2f}")
        return bal
    except Exception as e:
        print(f"FAILED: {e}")
        return None

def test_holdings(client):
    print("\n=== TEST: get_holdings_verified ===")
    try:
        h = client.get_holdings_verified()
        print(f"Holdings: {h}")
        return h.get("positions", {})
    except Exception as e:
        print(f"FAILED: {e}")
        return {}

def test_prices(client, pairs=None):
    print("\n=== TEST: get_price (live) ===")
    if pairs is None:
        pairs = ["ADA-USD", "ETH-USD", "BTC-USD"]
    results = {}
    for p in pairs:
        try:
            price = client.get_price(p)
            print(f"{p}: ${price}")
            results[p] = price
        except Exception as e:
            print(f"{p} FAILED: {e}")
    return results

def test_open_orders(client):
    print("\n=== TEST: get_open_orders + get_open_stop_orders ===")
    try:
        orders = client.get_open_orders()
        print(f"Open orders count: {len(orders) if orders else 0}")
        stops = client.get_open_stop_orders()
        print(f"Open stop orders count: {len(stops) if stops else 0}")
        return {"orders": orders, "stops": stops}
    except Exception as e:
        print(f"FAILED: {e}")
        return {"orders": [], "stops": []}

def test_place_small_buy(client, pair="ADA-USD", usd=5.0):
    print(f"\n=== TEST: place_market_buy {pair} ${usd} (SMALL TEST) ===")
    try:
        # Use the low-level for isolation
        result = client.place_market_buy(pair, usd)
        print(f"Buy result: {result}")
        return result
    except Exception as e:
        print(f"FAILED: {e}")
        return {"success": False, "error": str(e)}

def test_place_sell(client, pair="ADA-USD", size=30.0):
    print(f"\n=== TEST: place_market_sell {pair} size={size} ===")
    try:
        result = client.place_market_sell(pair, size)
        print(f"Sell result: {result}")
        return result
    except Exception as e:
        print(f"FAILED: {e}")
        return {"success": False, "error": str(e)}

def test_sl_attach(client, pair="ADA-USD", entry=0.16, size=30.0):
    print(f"\n=== TEST: attach_stop_loss {pair} ===")
    try:
        slm = StopLossManager(client, {"risk_management": {"stop_loss_pct": 0.03}}, mode="live")
        result = slm.attach_stop_loss(pair, entry, size)
        print(f"SL attach result: {result}")
        return result
    except Exception as e:
        print(f"FAILED: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--balance", action="store_true")
    parser.add_argument("--holdings", action="store_true")
    parser.add_argument("--prices", action="store_true")
    parser.add_argument("--orders", action="store_true")
    parser.add_argument("--buy-test", action="store_true")
    parser.add_argument("--sl-test", action="store_true")
    args = parser.parse_args()

    print("=== Coinbase API Full Diagnostic ===")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("Loading real credentials from .env...")

    client = CoinbaseExchangeClient(mode="live")
    print("Client initialized (live mode)")

    results = {}

    if args.all or args.balance:
        results["balance"] = test_balance(client)
    if args.all or args.holdings:
        results["holdings"] = test_holdings(client)
    if args.all or args.prices:
        results["prices"] = test_prices(client)
    if args.all or args.orders:
        results["orders"] = test_open_orders(client)

    if args.buy_test or args.all:
        # Very small test buy - user must be aware
        print("\nWARNING: --buy-test will place a REAL small order (~$5 ADA)")
        confirm = input("Type 'yes' to proceed with small buy test: ")
        if confirm.lower() == "yes":
            results["buy"] = test_place_small_buy(client)
            time.sleep(5)
            results["holdings_after_buy"] = test_holdings(client)
        else:
            print("Buy test skipped.")

    if args.sl_test or args.all:
        # Test SL on a small existing or hypothetical
        print("\nWARNING: --sl-test attempts real stop order placement")
        confirm = input("Type 'yes' to proceed with SL attach test: ")
        if confirm.lower() == "yes":
            results["sl"] = test_sl_attach(client)
        else:
            print("SL test skipped.")

    print("\n=== DIAGNOSTIC SUMMARY ===")
    for k, v in results.items():
        print(f"{k}: {v}")

    print("\nRecommendations logged to console. Fix issues in exchange_client.py and wrapper, then re-run.")

if __name__ == "__main__":
    main()
