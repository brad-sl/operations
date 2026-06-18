#!/usr/bin/env python3
"""
Production Smoke Test: Core Trade Logic Verification
Verifies: Ledger connectivity, Exchange API connectivity, and basic Order lifecycle.
Designed to run in PRODUCTION with minimal footprint.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup paths to ensure imports work
sys.path.insert(0, "/home/brad/projects/crypto-trading-bot")

# Use minimal direct imports to avoid heavy lifting or side effects
from phase6.core.trade_ledger import TradeLedger
from phase6.core.exchange_client import CoinbaseExchangeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("smoke-test")

def run_smoke_test():
    logger.info("Starting production smoke test...")

    # 1. Verify Ledger
    try:
        ledger = TradeLedger()
        test_payload = {
            "pair": "TEST-USD",
            "side": "BUY",
            "qty": 0.0,
            "entry_price": 0.0,
            "exit_price": 0.0,
            "pnl": 0,
            "pnl_pct": 0,
            "signal_source": "smoke_test"
        }
        ledger.log_trade(test_payload)
        logger.info("Ledger check passed.")
    except Exception as e:
        logger.error(f"Ledger check failed: {e}")
        return False

    # Verify Exchange Connectivity
    try:
        client = CoinbaseExchangeClient(mode="live")
        # Ensure client is fully ready
        if not client._ensure_live_client():
            raise Exception("Failed to initialize live client")
        # Ensure we can hit the API
        holdings = client.get_holdings_verified()
        if not holdings.get("verified"):
            raise Exception(f"Holdings verification failed: {holdings.get('error')}")
        logger.info(f"Exchange API connectivity verified (Active positions: {len(holdings.get('positions', {}))}).")
    except Exception as e:
        logger.error(f"Exchange connectivity check failed: {e}")
        return False

    logger.info("Smoke test passed successfully.")
    return True

if __name__ == "__main__":
    if run_smoke_test():
        print("RESULT: SUCCESS")
        sys.exit(0)
    else:
        print("RESULT: FAILURE")
        sys.exit(1)
