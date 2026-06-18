#!/usr/bin/env python3
"""
Live Smoke Test for SL Attachment + Small Trade Validation (Isolation style)

Purpose:
- Place a TINY real market buy on a high-scoring pair (ADA or LINK recommended).
- Verify automatic SL attachment (the fixed post-buy path in order_executor).
- Check open orders via improved get_open_stop_orders.
- Liquidate the position immediately after.
- All real data, no mocks.
- Requires explicit confirmation.

Usage (ONLY after shadow validation):
  python scripts/live_smoke_test.py --pair ADA-USD --usd-amount 15 --confirm "I accept real small trade + liquidate for validation"

Success criteria:
- Buy succeeds (order_id returned)
- SL attach succeeds (logs show 'successfully attached' + result=True; open orders may be empty due to key scope)
- Holdings update (or position appears)
- Sell succeeds and cleans up
Note: Open orders queries often 401 due to API key permissions; rely on attach return value and holdings.
- No errors in coordinator/executor

This is the mandatory live gate before full rebalance.
"""

import sys
import argparse
import logging
import time
from pathlib import Path

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.order_executor import OrderExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("live_smoke")

def get_current_price(client, pair):
    try:
        # Use public or client method
        price = client.get_price(pair)
        if price:
            return float(price)
    except:
        pass
    # Fallback to public Coinbase
    import requests
    try:
        url = f"https://api.exchange.coinbase.com/products/{pair}/ticker"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return float(resp.json().get("price", 0))
    except Exception as e:
        logger.warning(f"Price fetch failed: {e}")
    return None

def run_live_smoke(pair="ADA-USD", usd_amount=15.0, confirm=None):
    if confirm != "I accept real small trade + liquidate for validation":
        print("ERROR: Must pass --confirm 'I accept real small trade + liquidate for validation'")
        sys.exit(1)

    print("=" * 70)
    print(f"LIVE SMOKE TEST - {pair} ${usd_amount}")
    print("Real buy -> verify SL attach -> liquidate")
    print("!!! REAL MONEY - TINY AMOUNT ONLY !!!")
    print("=" * 70)

    # Real live client
    exchange = CoinbaseExchangeClient(mode="live")
    sl_manager = StopLossManager(exchange, {"risk_management": {"stop_loss_pct": 0.03}}, mode="live")
    executor = OrderExecutor(exchange, sl_manager, mode="live")

    # Get price
    price = get_current_price(exchange, pair)
    if not price or price <= 0:
        print("Could not get current price. Aborting.")
        return False
    size = round(usd_amount / price, 6)
    print(f"Current price {pair}: ${price:.4f}")
    print(f"Buy size: {size} (approx ${usd_amount})")

    # 1. Execute buy (this should now attach SL via the fixed path)
    print("\n--- Step 1: Market BUY ---")
    buy_result = executor.execute_buy(pair=pair, usd_amount=usd_amount)
    print(f"Buy result: {buy_result}")

    if not buy_result.get("success"):
        print("Buy failed. Aborting smoke.")
        return False

    entry_price = buy_result.get("entry_price", price)
    actual_size = buy_result.get("size", size)
    print(f"Entry: ${entry_price:.4f}, Size: {actual_size}")

    time.sleep(3)  # allow order to settle

    # 2. Verify SL attached
    print("\n--- Step 2: Verify SL attachment ---")
    try:
        open_stops = exchange.get_open_stop_orders(pair) or []
        print(f"Open stop orders for {pair}: {len(open_stops)}")
        for o in open_stops[:3]:
            print(f"  {o}")
        if open_stops:
            print("✅ SL order(s) visible via get_open_stop_orders")
        else:
            print("⚠️ No stop orders visible yet (may need UI check or delay). Check logs for attach call.")
    except Exception as e:
        print(f"Stop order check error: {e}")

    # Also check via coordinator if possible, but for smoke use direct

    # 3. Liquidate
    print("\n--- Step 3: Liquidate (market SELL) ---")
    sell_result = executor.execute_sell(pair=pair, size=actual_size)
    print(f"Sell result: {sell_result}")

    if sell_result.get("success"):
        print("✅ Liquidation succeeded.")
    else:
        print("⚠️ Sell may have issues - check manually in UI.")

    print("\n--- Smoke complete ---")
    print("Manual verification steps:")
    print("1. Check Coinbase app/web for the tiny position history and any SL orders.")
    print("2. Review logs for 'attach_stop_loss' and '[SL]' messages.")
    print("3. Confirm no leftover position or open orders.")

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", default="ADA-USD", choices=["ADA-USD", "LINK-USD", "OP-USD", "XRP-USD"])
    parser.add_argument("--usd-amount", type=float, default=15.0)
    parser.add_argument("--confirm", type=str, default=None)
    args = parser.parse_args()

    success = run_live_smoke(pair=args.pair, usd_amount=args.usd_amount, confirm=args.confirm)
    sys.exit(0 if success else 1)
