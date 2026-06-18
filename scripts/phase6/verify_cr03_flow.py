#!/usr/bin/env python3
"""
CR-03 Verification Script
Tests the full suspend → reattach flow using real positions from the live account.

This will:
1. Fetch real enriched positions
2. Suspend any existing protective orders
3. Re-attach fresh stop-loss orders using current data
4. Report results

WARNING: This performs real order operations on your live account.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()  # Load COINBASE_API_KEY / COINBASE_API_SECRET from .env

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.stop_loss_coordinator import StopLossCoordinator
from phase6.core.live_portfolio_manager import LivePortfolioManager

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cr03_verify")

def main():
    print("=" * 60)
    print("CR-03 Flow Verification (Live Mode)")
    print("=" * 60)

    # Initialize live client
    try:
        exchange = CoinbaseExchangeClient(mode="live")
    except Exception as e:
        print(f"Failed to initialize live exchange client: {e}")
        return

    # Get real positions
    portfolio = LivePortfolioManager(exchange)
    positions = portfolio.get_enriched_positions(force_refresh=True)

    if not positions:
        print("No positions returned from exchange. Exiting.")
        return

    print(f"\nFound {len(positions)} positions:")
    for pair, data in positions.items():
        print(f"  {pair}: {data.get('amount', 0):.4f} @ ${data.get('current_price', 0):.2f}")

    # Set up CR-03 components
    config = {"mode": "live", "require_atomic": True}
    sl_manager = StopLossManager(exchange, config, mode="live")
    coordinator = StopLossCoordinator(sl_manager, exchange_client=exchange, config=config)

    basket = list(positions.keys())

    print(f"\n--- Starting CR-03 suspend_reattach_context for {basket} ---")

    try:
        with coordinator.suspend_reattach_context(basket, positions):
            print("[Inside context] Rebalance window would happen here.")
            print("No actual rebalancing performed in this verification run.")
    except Exception as e:
        print(f"CR-03 flow failed: {e}")
        return

    print("\n--- CR-03 Flow Completed ---")
    print("Check your Coinbase account for newly placed stop orders.")
    print("Review logs/phase6_runner.log (or this output) for detailed results.")

if __name__ == "__main__":
    main()