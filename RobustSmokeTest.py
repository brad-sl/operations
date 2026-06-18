#!/usr/bin/env python3
"""
RobustSmokeTest.py — Diagnostic Smoke Test for Stop Loss Logic (MANUAL ONLY)

PURPOSE:
  Verifies StopLossManager precision handling (e.g. low-price assets like XRP/DOGE)
  and full lifecycle (detect_active_protective_orders / suspend / verify_reconciliation).
  All tests use mocked exchange classes only.

  THIS IS A DIAGNOSTIC / ACCESS-CHECK STYLE TEST.
  - NO live Coinbase API calls for trading
  - NO order placement, buys, sells, or position changes
  - NO real money or real data used
  - Runs in shadow/test_mode exclusively

  Distinct from:
  - prod_smoke_test.py   → live read-only connectivity + dummy ledger entry (0 qty TEST-USD)
  - live_smoke_test.py   → real small trade + liquidate (requires explicit --confirm)

STATUS:
  Hourly cron removed (redundant). The phase6 runner + frequent jobs (RSI 15m,
  sentiment 30m, monitors) already exercise live client init and access logic
  on a regular basis. Hourly smoke was overkill.

HOW TO RUN (manual only):
  cd /home/brad/projects/crypto-trading-bot
  python3 RobustSmokeTest.py

WHEN TO RUN:
  - Manually after changes to stop_loss_manager.py or SL precision logic.
  - Before promoting SL fixes.
  - Not scheduled.

NOTES / CAVEATS:
  - Import paths are fragile (sys.path hacks + direct imports of coinbase_advanced_client / stop_loss_manager).
    May need PYTHONPATH or project-root execution after refactors.
  - Currently fails on direct execution due to missing 'stop_loss_manager' (modules moved to phase6/core).
  - Keep this file strictly non-trading.

This file exists only for occasional isolated manual verification of SL behavior.
"""

import sys
import os
import logging
from decimal import Decimal

# Add path for imports
sys.path.append(os.path.abspath("./projects/crypto-trading-bot"))
sys.path.append(os.path.abspath("./projects/crypto-trading-bot/phase6/core"))

# Mock exchange
from coinbase_advanced_client import CoinbaseAdvancedClient
from stop_loss_manager import StopLossManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RobustSmokeTest")

def test_sl_precision():
    logger.info("--- Testing SL Precision (XRP/DOGE issues) ---")
    
    # Mocking a low-price asset
    class MockExchange(CoinbaseAdvancedClient):
        def get_product_metadata(self, product_id):
            return {"price_increment": "0.0001", "base_increment": "0.00000001"}
    
    exchange = MockExchange(test_mode=True)
    sl_manager = StopLossManager(exchange, {"risk_management": {"stop_loss_pct": 0.05}}, mode="shadow")
    
    # Test case: Low entry price
    entry_price = 0.5555  # XRP-ish
    size = 100.0
    
    logger.info(f"Entry Price: {entry_price}")
    # Call attach_stop_loss which now handles precision properly
    success = sl_manager.attach_stop_loss("XRP-USD", entry_price, size)
    
    if success:
        logger.info("✅ Precision test passed.")
    else:
        logger.error("❌ Precision test failed.")

def test_lifecycle():
    logger.info("\n--- Testing Lifecycle (Detect/Attach/Verify) ---")
    
    class MockExchangeLifecycle(CoinbaseAdvancedClient):
        def get_open_orders(self, **kwargs):
            return [{"id": "123", "product_id": "BTC-USD", "stop_price": "50000", "type": "STOP"}]
        def get_holdings(self):
            return {"BTC": 1.0}
        def get_product_metadata(self, product_id):
            return {"price_increment": "1.0", "base_increment": "0.001"}
            
    exchange = MockExchangeLifecycle(test_mode=True)
    sl_manager = StopLossManager(exchange, {"risk_management": {"stop_loss_pct": 0.03}}, mode="shadow")
    
    # Detec
    active = sl_manager.detect_active_protective_orders(["BTC-USD"])
    logger.info(f"Detected: {active}")
    
    # Suspend
    suspended = sl_manager.suspend_active_protective_orders(active)
    logger.info(f"Suspended: {suspended}")
    
    # Verify
    report = sl_manager.verify_reconciliation(["BTC-USD"], suspended)
    logger.info(f"Report: {report}")
    
    if report["success"]:
        logger.info("✅ Lifecycle test passed.")
    else:
        logger.error(f"❌ Lifecycle test failed: {report['details']}")

if __name__ == "__main__":
    test_sl_precision()
    test_lifecycle()
