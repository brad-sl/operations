#!/usr/bin/env python3
"""
Example Capital Event Monitor

This is a lightweight example of how an external process or runner
could detect capital events (new deposits or liquidations) and trigger
the deploy_capital function.

In a real system, this would be triggered by:
- Balance change detection
- Order fill / liquidation events
- Webhook or polling from the exchange
"""

import logging
from phase6.scripts.deploy_capital import deploy_capital

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("capital-monitor")


def on_capital_event(new_capital: float, source: str, current_allocations: dict, sentiment: dict):
    """
    Called when new capital is detected (deposit, liquidation, etc.).
    """
    logger.info(f"Capital event detected: ${new_capital:.2f} from {source}")

    new_allocations = deploy_capital(
        current_allocations=current_allocations,
        new_capital=new_capital,
        sentiment_scores=sentiment,
        source=source,
        candidate_pairs=["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "ADA-USD"],
        allow_new_pairs=True
    )

    logger.info(f"New allocations after deployment: {new_allocations}")
    return new_allocations


# ============================================================
# Example Usage
# ============================================================

if __name__ == "__main__":
    # Simulated state
    current_allocs = {"BTC-USD": 120.0, "ETH-USD": 90.0}
    latest_sentiment = {"BTC-USD": 0.55, "ETH-USD": -0.25, "SOL-USD": 0.42, "AVAX-USD": 0.38}

    # Simulate a liquidation event
    on_capital_event(
        new_capital=175.0,
        source="liquidation",
        current_allocations=current_allocs,
        sentiment=latest_sentiment
    )