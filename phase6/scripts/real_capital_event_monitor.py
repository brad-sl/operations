#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
Real Capital Event Monitor — Production Component

This module detects REAL capital events from LivePortfolioManager
and triggers the CapitalDeploymentRunner.

It contains NO simulation, NO random data, and NO test code.
It is designed to be the bridge between exchange balance reconciliation
and the capital deployment decision engine.
"""

import logging
from typing import Optional, Dict

from phase6.scripts.capital_deployment_runner import CapitalDeploymentRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("real-capital-monitor")


class RealCapitalEventMonitor:
    """Production monitor that feeds real events to the deployment runner."""

    def __init__(self, portfolio_manager, runner: CapitalDeploymentRunner):
        self.portfolio_manager = portfolio_manager
        self.runner = runner
        self.previous_positions: Dict[str, float] = {}

    def reconcile_and_detect_events(self) -> Optional[Dict]:
        """
        Compare current live positions with previous snapshot.
        Returns a capital event dict if a real change is detected, else None.
        """
        try:
            current = self.portfolio_manager.get_positions()
        except AttributeError:
            current = getattr(self.portfolio_manager, 'positions', {})
        if not current:
            return None

        if not self.previous_positions:
            self.previous_positions = current.copy()
            return None

        prev_total = sum(self.previous_positions.values())
        curr_total = sum(current.values())
        delta = curr_total - prev_total

        if abs(delta) < 5.0:  # Ignore noise
            self.previous_positions = current.copy()
            return None

        # Classify event type (simplified but based on real delta)
        if delta < -20:
            event_type = "liquidation"
        elif delta > 20:
            event_type = "deposit"
        else:
            event_type = "reserve_redeploy"

        event = {
            "type": event_type,
            "amount": round(abs(delta), 2),
            "previous_total": round(prev_total, 2),
            "current_total": round(curr_total, 2),
        }

        logger.info(f"REAL event detected: {event}")
        self.previous_positions = current.copy()
        return event

    def process_real_event(self, event: Dict, sentiment: Dict, candidates: list):
        """Feed the real event into the runner."""
        self.runner.set_sentiment_and_candidates(sentiment, candidates)
        return self.runner.process_capital_event(event["type"], event["amount"])


if __name__ == "__main__":
    print("RealCapitalEventMonitor ready. Instantiate with real LivePortfolioManager + Runner.")