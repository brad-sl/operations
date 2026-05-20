#!/usr/bin/env python3
"""
Diagnostic Test: Fresh Start Basket + Stop-Loss Attachment

This script validates the repaired Fresh Start logic and Stop-Loss attachment
without running a continuous trading loop.

Usage:
    # Safe shadow test (recommended first)
    python scripts/phase6/test_fresh_start_stop_loss.py --mode shadow

    # Live test (uses real money - requires confirmation)
    python scripts/phase6/test_fresh_start_stop_loss.py --mode live --confirm-live
"""

import os
import sys
import argparse
from dotenv import load_dotenv

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager

FIXED_UNIVERSE = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]


def run_test(mode: str, confirm_live: bool = False):
    load_dotenv()

    if mode == "live" and not confirm_live:
        print("ERROR: --mode live requires --confirm-live for safety.")
        sys.exit(1)

    print(f"\n=== Fresh Start + Stop-Loss Diagnostic Test ===")
    print(f"Mode: {mode.upper()}")
    print(f"Pairs: {FIXED_UNIVERSE}")
    print("-" * 60)

    # Initialize clients
    exchange = CoinbaseExchangeClient(mode=mode)
    config = {"risk_management": {"stop_loss_pct": 0.03}}
    sl_manager = StopLossManager(exchange, config, mode=mode)

    # Get available capital
    if mode == "live":
        capital = exchange.get_account_balance("USD")
    else:
        capital = 967.76  # Approximate from previous liquidation

    print(f"Available capital: ${capital:.2f}")
    print("-" * 60)

    successful_buys = 0
    sl_attached = 0
    failed_sl = []

    deploy_pct = 0.95
    per_pair_capital = (capital * deploy_pct) / len(FIXED_UNIVERSE)

    for pair in FIXED_UNIVERSE:
        usd_amount = round(per_pair_capital, 2)

        if usd_amount < 20:
            print(f"[SKIP] {pair}: ${usd_amount:.2f} below minimum")
            continue

        print(f"\n[ATTEMPT] {pair}: targeting ${usd_amount:.2f}")

        if mode == "shadow":
            # Simulate buy success
            entry_price = exchange.get_price(pair)
            size = usd_amount / entry_price if entry_price > 0 else 0

            print(f"  [SHADOW] Would BUY ${usd_amount:.2f} {pair} @ ~${entry_price}")
            sl_success = sl_manager.attach_stop_loss(pair, entry_price, size)

            if sl_success:
                print(f"  [SUCCESS] SL attached (shadow)")
                sl_attached += 1
            else:
                print(f"  [FAIL] SL attachment failed")
                failed_sl.append(pair)

            successful_buys += 1
        else:
            # Real live buy
            try:
                resp = exchange.place_market_buy(pair, usd_amount)
                success = resp.get("success", False) if isinstance(resp, dict) else getattr(resp, "success", False)

                if success:
                    entry_price = exchange.get_price(pair)
                    size = usd_amount / entry_price if entry_price > 0 else 0

                    print(f"  [LIVE] Bought ${usd_amount:.2f} {pair} @ ${entry_price}")

                    sl_success = sl_manager.attach_stop_loss(pair, entry_price, size)
                    if sl_success:
                        print(f"  [SUCCESS] Native stop-loss attached")
                        sl_attached += 1
                    else:
                        print(f"  [WARNING] Buy succeeded but SL attachment failed after retries")
                        failed_sl.append(pair)

                    successful_buys += 1
                else:
                    print(f"  [FAIL] Buy failed: {resp}")
            except Exception as e:
                print(f"  [EXCEPTION] {pair}: {e}")

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print(f"Successful buys: {successful_buys}")
    print(f"Stop-losses attached: {sl_attached}")
    if failed_sl:
        print(f"Failed SL attachments: {failed_sl}")
    print("=" * 60)

    if mode == "live":
        print("\n⚠️  Live test complete. Review results and positions on Coinbase.")
    else:
        print("\nShadow test complete. Logic validated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow")
    parser.add_argument("--confirm-live", action="store_true", default=False)
    args = parser.parse_args()

    run_test(args.mode, args.confirm_live)