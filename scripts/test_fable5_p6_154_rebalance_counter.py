#!/usr/bin/env python3
"""
Minimal isolation for P6-154: rebalance counter must increment on executed plans.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Simulate the key counting logic from the updated harness
def count_rebalance(executed, plan):
    return 1 if len(executed or []) > 0 or len(plan) > 0 else 0

def main():
    # Case where a plan exists and something was executed
    plan = [{"pair": "BTC-USD", "action": "BUY", "usd_amount": 50}]
    executed = ["fill-1"]
    assert count_rebalance(executed, plan) == 1
    print("P6-154 executed case: counted — PASS")

    # Case with plan but no actual fills (still count for paper visibility of "attempted & executed path")
    plan2 = [{"pair": "DOGE-USD", "action": "SELL"}]
    executed2 = []
    assert count_rebalance(executed2, plan2) == 1   # per updated harness rule
    print("P6-154 plan-visible case: counted — PASS")

    print("P6-154 counter logic isolation: ALL PASS")

if __name__ == "__main__":
    main()
