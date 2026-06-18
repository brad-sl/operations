#!/usr/bin/env python3
"""
Smoke test for Phase 6 Sentiment Sub-system

Tests:
- Loading X + Reddit caches (with decay)
- Combined scoring
- Sentiment-adjusted weights

Run this to validate the sentiment system is working before backtesting.
"""

import sys
from pathlib import Path

# Add phase6 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.sentiment.sentiment_scorer import (
    load_sentiment_scores,
    get_sentiment_adjusted_weights
)

def main():
    print("=" * 60)
    print("PHASE 6 SENTIMENT SYSTEM - SMOKE TEST")
    print("=" * 60)

    # Test 1: Load sentiment scores
    print("\n[1] Loading sentiment scores with time decay...")
    try:
        scores = load_sentiment_scores()
        print(f"    ✓ Loaded scores for {len(scores)} pairs")
        
        for pair, data in list(scores.items())[:3]:
            print(f"    {pair}: combined={data['combined']:.4f} | "
                  f"X(decayed)={data['x']['decayed']:.4f} | "
                  f"Reddit(decayed)={data['reddit']['decayed']:.4f}")
    except Exception as e:
        print(f"    ✗ Failed: {e}")
        return False

    # Test 2: Apply to sample allocation weights
    print("\n[2] Testing sentiment-adjusted weights...")
    try:
        base_weights = {
            "BTC-USD": 0.35,
            "ETH-USD": 0.25,
            "SOL-USD": 0.20,
            "XRP-USD": 0.12,
            "DOGE-USD": 0.08
        }
        
        adjusted = get_sentiment_adjusted_weights(base_weights, scores)
        print("    ✓ Adjusted weights generated")
        
        for pair in base_weights:
            base = base_weights[pair]
            adj = adjusted.get(pair, 0)
            print(f"    {pair}: {base:.4f} → {adj:.4f}")
    except Exception as e:
        print(f"    ✗ Failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ SENTIMENT SYSTEM SMOKE TEST PASSED")
    print("=" * 60)
    print("\nThe sentiment sub-system is now working and ready for backtesting.")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)