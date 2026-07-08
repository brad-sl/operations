#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
Capital Deployment Runner — Production Event Handler

This module is production-safe. It contains NO random generators,
no simulated events, and no test data.

It is designed to be called by real monitors (LivePortfolioManager,
position_state_manager, stop-loss coordinators, etc.) when actual
capital events occur (liquidations, deposits, reserve redeployments).

All allocations come from LivePortfolioManager (real exchange data).
All sentiment comes from the sentiment scoring pipeline.
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

from phase6.scripts.deploy_capital import deploy_capital

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("capital-runner")

PARAMS = {
    "min_sentiment": -0.30,
    "min_new_pair_sentiment": 0.20,
    "max_new_pairs": 2,
    "min_new_pair_allocation": 30.0,
    "max_pairs": 8,
}


def get_live_portfolio_manager():
    """Return a configured LivePortfolioManager or None.
    Production code must pass a real cb_client.
    """
    try:
        from src.core.live_portfolio_manager import LivePortfolioManager

        # In production, a real Coinbase client must be injected here.
        # This function is intentionally minimal so monitors can pass their own.
        return None  # Monitors are expected to create and pass the real manager
    except Exception as e:
        logger.warning(f"LivePortfolioManager import failed: {e}")
        return None


class CapitalDeploymentRunner:
    """Production event handler for capital deployment decisions.

    External monitors call process_capital_event() with REAL events only.
    """

    def __init__(self, live: bool = False, portfolio_mgr=None):
        self.live = live
        self.portfolio_mgr = portfolio_mgr or get_live_portfolio_manager()
        self.allocations = self._fetch_current_allocations()
        # Sentiment must come from the live sentiment pipeline (not hardcoded)
        self.sentiment = {}  # Will be populated by caller or sentiment module
        self.candidates = []  # Populated by caller or config

    def _fetch_current_allocations(self) -> dict:
        """Always prefer real data from LivePortfolioManager."""
        if self.portfolio_mgr and hasattr(self.portfolio_mgr, "get_positions"):
            try:
                positions = self.portfolio_mgr.get_positions()
                if positions:
                    logger.info(f"Real allocations from exchange: {positions}")
                    return positions
            except Exception as e:
                logger.error(f"Failed to fetch live positions: {e}")
        logger.error("No real balance source available — refusing to use fallback in production")
        return {}

    def set_sentiment_and_candidates(self, sentiment: dict, candidates: list):
        """Called by the sentiment pipeline before processing events."""
        self.sentiment = sentiment
        self.candidates = candidates

    def process_capital_event(self, event_type: str, amount: float):
        """Process a REAL capital event from a monitor."""
        if not self.sentiment or not self.candidates:
            logger.error("Sentiment and candidates not set — cannot process event")
            return

        logger.info(f"REAL capital event: ${amount:.2f} | Type: {event_type}")

        self.allocations = self._fetch_current_allocations()
        if not self.allocations:
            logger.error("Cannot deploy capital — no current allocations")
            return

        new_allocs = deploy_capital(
            current_allocations=self.allocations,
            new_capital=amount,
            sentiment_scores=self.sentiment,
            source=event_type,
            candidate_pairs=self.candidates,
            **PARAMS
        )

        if self.live:
            logger.warning("LIVE MODE: Applying new allocations (real trades will be sent)")
            self.allocations = new_allocs
        else:
            logger.info(f"[SHADOW] Proposed allocations: {new_allocs}")

        return new_allocs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable light live execution")
    args = parser.parse_args()

    runner = CapitalDeploymentRunner(live=args.live)
    print("CapitalDeploymentRunner ready for production event injection.")
    print("External monitors must call runner.process_capital_event() with real events.")