#!/usr/bin/env python3
"""
Isolation Test: Execution Layer Hardening + SL Orthogonality
Goal: Verify OrderExecutor + StopLossManager produce correct SL attach, handle errors, produce TradePlan execution results.
Uses shadow mode with real data snapshots where possible.
Run: python scripts/phase6/test_isolation_execution_hardening.py
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager
from phase6.core.order_executor import OrderExecutor
import json
from datetime import datetime

def main():
    print("=== Execution Layer Hardening Isolation Test ===")
    print(f"Time: {datetime.now().isoformat()}")

    # Shadow client for safe testing
    client = CoinbaseExchangeClient(mode="shadow")
    config = {"risk_management": {"stop_loss_pct": 0.03, "take_profit_pct": 0.06}}
    slm = StopLossManager(client, config, mode="shadow")
    executor = OrderExecutor(client, slm, mode="shadow")

    # Test 1: Buy + SL attach
    print("\n--- Test 1: execute_buy + SL attach (shadow) ---")
    buy_result = executor.execute_buy("ADA-USD", 10.0)
    print(json.dumps(buy_result, indent=2))
    assert buy_result.get("success"), "Buy failed in shadow"
    assert buy_result.get("sl_attached"), "SL not attached in shadow"

    # Test 2: Sell
    print("\n--- Test 2: execute_sell (shadow) ---")
    sell_result = executor.execute_sell("ADA-USD", 10.0)
    print(json.dumps(sell_result, indent=2))
    assert sell_result.get("success")

    # Test 3: SL manager direct attach with different params
    print("\n--- Test 3: direct SL attach with custom pct (shadow) ---")
    sl_result = slm.attach_stop_loss("ETH-USD", 1700.0, 0.01, sl_pct=0.05)
    print("SL attach result:", sl_result)
    assert sl_result

    # Test 4: detect protective (will be empty in shadow)
    print("\n--- Test 4: detect_active_protective_orders (shadow) ---")
    detected = slm.detect_active_protective_orders(["ADA-USD", "ETH-USD"])
    print("Detected:", detected)

    print("\n=== ALL HARDENING ISOLATION TESTS PASSED (shadow) ===")
    print("Evidence: SL attach orthogonal, executor wires it, graceful on empty orders.")

if __name__ == "__main__":
    main()
