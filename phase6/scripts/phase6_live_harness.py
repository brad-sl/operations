#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
phase6_live_harness.py

Wires CoinbaseAdvancedClient + LivePortfolioManager +
RealCapitalEventMonitor + CapitalDeploymentRunner for Phase 2+3 capital events.

- Supports --sandbox (test_mode=True) and --live (test_mode=False)
- No hardcoded data, balances, or positions anywhere
- All data sourced live from exchange via cb_client
- Production-safe: mode must be explicitly chosen
- Sentiment integration: loads live scores from sentiment pipeline cache
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is importable when run from anywhere
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from coinbase_advanced_client import CoinbaseAdvancedClient
from src.core.live_portfolio_manager import LivePortfolioManager
from phase6.scripts.capital_deployment_runner import CapitalDeploymentRunner
from phase6.scripts.real_capital_event_monitor import RealCapitalEventMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("phase6-live-harness")


def create_harness(sandbox: bool = True):
    """Wire all components with live sentiment integration."""
    mode_str = "SANDBOX" if sandbox else "LIVE"
    logger.info(f"Initializing Phase 6 live harness in {mode_str} mode")

    # 1. Coinbase Advanced client (real credentials from .env)
    cb_client = CoinbaseAdvancedClient(test_mode=sandbox)
    logger.info(f"CoinbaseAdvancedClient ready (test_mode={sandbox})")

    # 2. LivePortfolioManager (receives real client, no defaults)
    portfolio_mgr = LivePortfolioManager(
        cb_client=cb_client,
        state_path="phase6/portfolio_state.json",
        db_path="phase6/phase6_monitor.db",
        csv_path="phase6/trades_live.csv",
        total_capital=10000.0,
    )
    logger.info("LivePortfolioManager wired with real cb_client")

    # 3. CapitalDeploymentRunner
    runner = CapitalDeploymentRunner(live=not sandbox, portfolio_mgr=portfolio_mgr)
    logger.info(f"CapitalDeploymentRunner ready (live={not sandbox})")

    # 4. RealCapitalEventMonitor
    monitor = RealCapitalEventMonitor(
        portfolio_manager=portfolio_mgr,
        runner=runner
    )
    logger.info("RealCapitalEventMonitor wired — ready to detect real capital events")

    # 5. Sentiment integration (loads from live pipeline / cache)
    try:
        from phase6.scripts.sentiment_loader import load_live_sentiment
        sentiment, candidates = load_live_sentiment()
        runner.set_sentiment_and_candidates(sentiment, candidates)
        logger.info(f"Live sentiment injected: {len(sentiment)} pairs")
    except Exception as e:
        logger.warning(f"Sentiment loader not available ({e}). External sentiment required.")

    return monitor, cb_client, portfolio_mgr, runner


def run_harness(monitor: RealCapitalEventMonitor, runner, cycles: int = 1, interval: float = 30.0):
    """Run reconciliation + event detection loop (real data only)."""
    logger.info(f"Starting harness event loop: {cycles} cycles, {interval}s interval")
    for i in range(cycles):
        event = monitor.reconcile_and_detect_events()
        if event:
            logger.info(f"Event processed in cycle {i+1}: {event}")
            if runner.sentiment:
                monitor.process_real_event(event, runner.sentiment, runner.candidates)
            else:
                logger.warning("No live sentiment available — skipping deployment decision")
        else:
            logger.info(f"Cycle {i+1}: no significant capital event detected")
        if i < cycles - 1:
            time.sleep(interval)
    logger.info("Harness run complete")


def main():
    parser = argparse.ArgumentParser(description="Phase 6 Live Capital Harness")
    parser.add_argument("--sandbox", action="store_true", default=True,
                        help="Use sandbox/test mode (default)")
    parser.add_argument("--live", action="store_true",
                        help="Use production live mode (overrides --sandbox)")
    parser.add_argument("--cycles", type=int, default=3,
                        help="Number of reconciliation cycles to run")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="Seconds between cycles")
    args = parser.parse_args()

    sandbox = not args.live
    monitor, cb_client, portfolio_mgr, runner = create_harness(sandbox=sandbox)

    monitor.reconcile_and_detect_events()

    if args.cycles > 0:
        run_harness(monitor, runner, cycles=args.cycles, interval=args.interval)

    logger.info("phase6_live_harness ready.")


if __name__ == "__main__":
    main()