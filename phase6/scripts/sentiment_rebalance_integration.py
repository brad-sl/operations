#!/usr/bin/env python3
"""
Sentiment + Rebalancing Integration Module

Wires the sentiment scorer into the Phase 6 rebalancing flow while
keeping all sentiment logic in a separate, maintainable module.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List

# Ensure the project root is importable when running this module directly
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def apply_sentiment_to_allocations(
    allocations: Dict[str, float],
    pairs: List[str],
    sentiment_weight: float = 0.20
) -> Dict[str, float]:
    """
    Apply sentiment-weighted adjustment to current allocations.

    This is the clean integration point between the rebalancing engine
    and the sentiment system.
    """
    try:
        from scripts.sentiment_scorer import load_sentiment_scores, get_sentiment_adjusted_weights

        current_sentiment = load_sentiment_scores(universe=pairs)
        logger.info(f"Sentiment scores loaded: {current_sentiment}")

        adjusted = get_sentiment_adjusted_weights(
            base_weights=allocations,
            sentiment_scores=current_sentiment,
            sentiment_weight=sentiment_weight
        )

        logger.info(f"Sentiment adjustment applied (weight={sentiment_weight})")
        return adjusted

    except Exception as e:
        logger.warning(f"Sentiment adjustment skipped: {e}")
        return allocations


# ============================================================
# Validation Test
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_allocations = {
        "BTC-USD": 200.0,
        "ETH-USD": 200.0,
        "SOL-USD": 200.0,
    }
    test_pairs = list(test_allocations.keys())

    print("=== Sentiment Rebalancing Integration Test ===")
    result = apply_sentiment_to_allocations(test_allocations, test_pairs)

    print("\nFinal allocations after sentiment adjustment:")
    for pair, amount in result.items():
        print(f"  {pair}: ${amount:.2f}")

    print(f"\nTotal: ${sum(result.values()):.2f}")
    print("Test completed.")