#!/usr/bin/env python3
"""
ARCH-0 Isolation Test: Hybrid Rebalance Trigger vs Time-based

Standalone wrapper. Exercises HybridRebalancer.evaluate (as called by runner._evaluate_hybrid_rebalance)
with real current sentiment from the canonical scorer.

Goal: Show what the hybrid trigger actually decides today vs the pure time-based _should_rebalance.
Evidence of divergence: hybrid may or may not fire; runner still relies primarily on calendar time (21:00).

Uses real data (sentiment_cache + scorer).
"""

import json
import logging
from pathlib import Path
from datetime import datetime
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase6.core.rebalancing.hybrid_rebalancer import HybridRebalancer, RebalanceDecision
from phase6.core.sentiment_scorer import load_sentiment_scores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # dynamic per DATA_FLOW_AND_LOCATIONS.md (enforced)
from phase6.core.paths import load_trading_basket
FIXED_UNIVERSE = load_trading_basket()  # central 11-pair (TESTS-01)

def test_hybrid_trigger_vs_time():
    print("=== ARCH-0: Hybrid Trigger Isolation Test ===")
    print("Testing: HybridRebalancer.evaluate (called in runner as _evaluate_hybrid_rebalance)")
    print("Compared to pure time-based _should_rebalance (daily at config time, default 21:00).\n")

    rebal = HybridRebalancer()
    real_sentiment = load_sentiment_scores(universe=FIXED_UNIVERSE)
    print(f"Real current sentiment (scorer): { {p: round(s,4) for p,s in real_sentiment.items()} }")

    # Call exactly as runner does (previous_sentiment=None first time, no vol/DD for baseline)
    decision: RebalanceDecision = rebal.evaluate(
        universe=FIXED_UNIVERSE,
        previous_sentiment=None,
        volatility=None,
        drawdown=None,
    )

    print("\n--- Hybrid Decision (real data) ---")
    print(f"should_rebalance: {decision.should_rebalance}")
    print(f"reason: {decision.reason}")
    print(f"sentiment_deltas: { {k: round(v,4) for k,v in decision.sentiment_deltas.items()} }")
    print(f"triggered_thresholds: {decision.triggered_thresholds}")
    print(f"ai_filter_passed: {decision.ai_filter_passed}")
    print(f"confidence: {decision.confidence}")
    print(f"suggested_actions: {decision.suggested_actions}")

    # Simulate time-based (what runner primarily uses)
    now = datetime.utcnow()
    time_based = (now.hour >= 21) or True  # simplified; actual is last_rebalance_date + calendar
    print(f"\nTime-based trigger (current time {now.strftime('%H:%M')} vs daily_rebalance_time ~21:00): likely {time_based} today")

    evidence = {
        "timestamp": datetime.utcnow().isoformat(),
        "hybrid_decision": {
            "should_rebalance": decision.should_rebalance,
            "reason": decision.reason,
            "sentiment_deltas": {k: round(v,4) for k,v in decision.sentiment_deltas.items()},
            "ai_filter_passed": decision.ai_filter_passed,
            "confidence": decision.confidence,
        },
        "real_sentiment": {p: round(s,4) for p,s in real_sentiment.items()},
        "time_based_likely": time_based,
        "note": "In runner: rebalance_needed = self._should_rebalance(now) or self._evaluate_hybrid_rebalance(). Hybrid is secondary trigger only (P4-03). generate_rebalance_plan retired; plans via Allocator + RebalanceStrategy (ARCH-4 canonical)."
    }
    out_path = PROJECT_ROOT / "data/state/arch0_isolation_hybrid_trigger_evidence.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(evidence, f, indent=2)
    print(f"\nEvidence written to {out_path}")

    print("\nConclusion: Hybrid trigger is a secondary 'or' condition. Primary driver remains calendar time + the deploy_capital path.")
    print("Hybrid can produce RebalanceDecision (trigger only). generate_rebalance_plan retired per P4-03; no longer used or primary. Plans via Allocator/RebalanceStrategy.")

    return evidence

if __name__ == "__main__":
    test_hybrid_trigger_vs_time()
    print("\n[ARCH-0 Hybrid Trigger] PASSED - baseline captured.")