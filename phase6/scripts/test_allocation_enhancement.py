#!/usr/bin/env python3
"""
Test suite for Allocation Engine Enhancement (Liquidity Bias + Sentiment)
Run with: python test_allocation_enhancement.py
"""

import unittest
from enhanced_allocation_engine import (
    compute_enhanced_allocations,
    apply_liquidity_bias,
    apply_sentiment_adjustment,
    apply_holding_proportional_bias,
    rebalance_plan_enhanced
)

class TestEnhancedAllocation(unittest.TestCase):

    def test_liquidity_bias_favors_high_liq(self):
        base = {"BTC-USD": 0.4, "ALT-USD": 0.6}
        liq = {"BTC-USD": 0.9, "ALT-USD": 0.3}
        adj = apply_liquidity_bias(base, liq, liquidity_weight=0.4)
        self.assertGreater(adj["BTC-USD"], base["BTC-USD"] * 0.9)  # boosted
        self.assertLess(adj["ALT-USD"], base["ALT-USD"] * 1.1)

    def test_sentiment_adjustment(self):
        base = {"BTC-USD": 0.5, "DOGE-USD": 0.5}
        sent = {"BTC-USD": 0.6, "DOGE-USD": -0.4}
        adj = apply_sentiment_adjustment(base, sent, sentiment_weight=0.3)
        self.assertGreater(adj["BTC-USD"], 0.5)
        self.assertLess(adj["DOGE-USD"], 0.5)

    def test_holding_proportional_bias(self):
        base = {"BTC-USD": 0.6, "NEW-USD": 0.4}
        curr = {"BTC-USD": 8000.0}  # only holding BTC
        adj = apply_holding_proportional_bias(base, curr, holding_bias=0.5)
        self.assertGreater(adj["BTC-USD"], 0.6)
        self.assertLess(adj.get("NEW-USD", 0), 0.4)

    def test_full_enhanced_pipeline(self):
        vols = {"BTC-USD": 0.9, "ETH-USD": 1.4, "SOL-USD": 2.8}
        liq = {"BTC-USD": 0.92, "ETH-USD": 0.78, "SOL-USD": 0.55}
        sent = {"BTC-USD": 0.35, "ETH-USD": 0.15, "SOL-USD": -0.25}
        curr = {"BTC-USD": 5200.0, "ETH-USD": 2800.0}
        weights = compute_enhanced_allocations(
            vols, liq, sent, curr,
            total_capital=10000.0,
            withdrawal_reserve_usd=650.0,
            min_reserve_usd=500.0
        )
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)
        # BTC should be favored (high liq + positive sent + held)
        self.assertGreater(weights["BTC-USD"], 0.45)
        # SOL penalized
        self.assertLess(weights["SOL-USD"], 0.25)

    def test_withdrawal_reserve_caps_deployment(self):
        # Reserve enforcement happens in withdrawal_reserve.py; here weights always ~sum to 1
        weights = compute_enhanced_allocations(
            {"BTC-USD": 1.0}, {"BTC-USD": 0.8}, {"BTC-USD": 0.0},
            total_capital=5000.0, withdrawal_reserve_usd=4500.0, min_reserve_usd=4000.0
        )
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=4)
        self.assertGreater(weights["BTC-USD"], 0.9)

    def test_rebalance_plan(self):
        curr = {"BTC-USD": 3000.0}
        targets = {"BTC-USD": 0.6, "ETH-USD": 0.4}
        plan = rebalance_plan_enhanced(curr, targets, 10000.0, min_move=50.0)
        self.assertTrue(any(p["action"] == "BUY" for p in plan))
        self.assertTrue(any(p["pair"] == "ETH-USD" for p in plan))

if __name__ == "__main__":
    unittest.main(verbosity=2)
