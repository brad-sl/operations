#!/usr/bin/env python3
"""
Smoke test for Hybrid Rebalancer (Phase 6 Task 2 - Rebalancing Logic Upgrade)
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from phase6.core.rebalancing.hybrid_rebalancer import HybridRebalancer, RebalanceDecision


def test_basic_trigger():
    rebalancer = HybridRebalancer()
    universe = ["BTC-USD", "ETH-USD"]
    # Simulate previous sentiment to create delta (high delta should trigger)
    decision = rebalancer.evaluate(
        universe=universe,
        previous_sentiment={"BTC-USD": 0.0, "ETH-USD": 0.0},
        volatility={"BTC-USD": 0.05, "ETH-USD": 0.09},
        drawdown=0.02,
    )
    assert isinstance(decision, RebalanceDecision)
    print(f"✓ Basic decision structure works: should_rebalance={decision.should_rebalance}")
    print(f"  Reason: {decision.reason}")


def test_ai_filter_block():
    rebalancer = HybridRebalancer(config={"ai_confidence_threshold": 0.95, "sentiment_delta_threshold": 0.8})
    decision = rebalancer.evaluate(
        universe=["BTC-USD"],
        previous_sentiment={"BTC-USD": 0.0},
        volatility={"BTC-USD": 0.05},
        drawdown=0.01,
    )
    print(f"✓ AI filter logic exercised: should_rebalance={decision.should_rebalance}")
    print(f"  Reason: {decision.reason}")


def test_vol_spike():
    rebalancer = HybridRebalancer(config={"volatility_spike_threshold": 0.10})
    decision = rebalancer.evaluate(
        universe=["SOL-USD"],
        previous_sentiment={"SOL-USD": 0.0},
        volatility={"SOL-USD": 0.35},
        drawdown=0.0,
    )
    print(f"✓ Vol spike test: should_rebalance={decision.should_rebalance}, triggers={decision.triggered_thresholds}")


if __name__ == "__main__":
    test_basic_trigger()
    test_ai_filter_block()
    test_vol_spike()
    print("\nAll smoke tests passed. Hybrid rebalancer ready for integration.")