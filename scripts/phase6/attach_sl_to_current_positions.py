#!/usr/bin/env python3
"""
Attach Stop-Loss to Current Live Positions

This script queries your current Coinbase holdings and attaches
3% native stop-loss orders to each crypto position.

Usage:
    python scripts/phase6/attach_sl_to_current_positions.py --confirm-live
"""

import os
import sys
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager

DEFAULT_SL_PCT = 0.03
BUFFER = 0.995  # 0.5% buffer below stop price


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", default=False,
                        help="Required to run against real money")
    args = parser.parse_args()

    if not args.confirm_live:
        print("ERROR: This script modifies live positions. Use --confirm-live to proceed.")
        sys.exit(1)

    load_dotenv()

    print("=== Attach Stop-Loss to Current Positions ===")
    print("Mode: LIVE")
    print("-" * 50)

    exchange = CoinbaseExchangeClient(mode="live")
    config = {"risk_management": {"stop_loss_pct": DEFAULT_SL_PCT}}
    sl_manager = StopLossManager(exchange, config, mode="live")

    # Get current holdings
    accounts = exchange.real_client.get_accounts()
    holdings = {}

    for acc in accounts.get("accounts", []):
        currency = acc.get("currency")
        balance = float(acc.get("available_balance", {}).get("value", 0))
        if currency != "USD" and balance > 0:
            holdings[currency] = balance

    print(f"Current holdings: {holdings}")
    print("-" * 50)

    attached = []
    failed = []

    for currency, qty in holdings.items():
        pair = f"{currency}-USD"

        # Get current price
        price = exchange.get_price(pair)
        if price <= 0:
            print(f"[SKIP] {pair}: Could not get valid price")
            continue

        stop_price = round(price * (1 - DEFAULT_SL_PCT), 2)
        limit_price = round(stop_price * BUFFER, 2)

        print(f"\n[{pair}]")
        print(f"  Quantity: {qty}")
        print(f"  Current Price: ${price:,.2f}")
        print(f"  Stop Price (3%): ${stop_price:,.2f}")
        print(f"  Limit Price: ${limit_price:,.2f}")

        success = sl_manager.attach_stop_loss(pair, price, qty)

        if success:
            print(f"  ✅ Stop-loss attached successfully")
            attached.append(pair)
        else:
            print(f"  ❌ Failed to attach stop-loss after retries")
            failed.append(pair)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print(f"Stop-losses attached: {len(attached)} → {attached}")
    if failed:
        print(f"Failed: {len(failed)} → {failed}")
    print("=" * 50)


if __name__ == "__main__":
    main()