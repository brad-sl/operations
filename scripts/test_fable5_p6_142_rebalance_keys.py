#!/usr/bin/env python3
"""
Code Isolation Test for P6-142 (rebalance_plan key consistency).
rebalance_plan must consistently use "usd_value" (or value_usd) keys that LPM / runner / paper_trader understand.
No bare numeric "usd_value" in nested dicts causing KeyErrors downstream.
"""
import sys
sys.path.insert(0, ".")
from scripts.allocation_engine import rebalance_plan

def test_rebalance_plan_key_shape():
    # Simulate current positions coming from LPM (value_usd) or old runner (usd_value)
    current = {
        "BTC-USD": {"usd_value": 300},
        "DOGE-USD": 120.0,   # bare float (legacy)
    }
    target = {"BTC-USD": 0.4, "DOGE-USD": 0.3}
    plan = rebalance_plan(current, target, total_capital=1000.0)
    assert isinstance(plan, list)
    # Must not crash on mixed shapes
    # Check plan items have the expected action keys
    for move in plan:
        assert "action" in move and move["action"] in ("BUY", "SELL")
        assert "usd_amount" in move
    print("P6-142: rebalance_plan handles mixed 'usd_value' / bare-float current positions.")
    # Additional: assert plan respects reserve-like scaling (no massive moves)
    for move in plan:
        assert move["usd_amount"] <= 300, "Plan should not propose huge moves on small total_capital"

if __name__ == "__main__":
    test_rebalance_plan_key_shape()
    print("P6-142 isolation test: PASS")
