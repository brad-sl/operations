#!/usr/bin/env python3
"""
Phase 6 Fresh Start Diagnostic Script

Validates that _handle_fresh_start() attempts buys across the FULL FIXED_UNIVERSE.

Usage:
  # Shadow mode (safe, recommended first)
  python scripts/phase6_diagnostic_fresh_start.py --config path/to/config.json --mode shadow

  # Live mode (use with caution, small capital only)
  python scripts/phase6_diagnostic_fresh_start.py --config path/to/config.json --mode live --force-fresh

This script forces a fresh-start path by temporarily clearing positions (shadow) or
by direct invocation of the fresh start handler.
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase6.core.phase6_runner import Phase6Runner

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("phase6.diagnostic")


def main():
    parser = argparse.ArgumentParser(description="Phase 6 Fresh Start Basket Validation Diagnostic")
    parser.add_argument("--config", required=True, help="Path to trading_config_phase6.json")
    parser.add_argument("--mode", choices=["shadow", "live"], default="shadow",
                        help="Run in shadow (safe) or live mode")
    parser.add_argument("--force-fresh", action="store_true",
                        help="Force fresh start path even if positions exist (shadow only)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("PHASE 6 FRESH START BASKET VALIDATION DIAGNOSTIC")
    logger.info(f"Mode: {args.mode.upper()} | Config: {args.config}")
    logger.info("=" * 60)

    runner = Phase6Runner(config_path=args.config, mode=args.mode)

    # For diagnostic purposes we always want to exercise the fresh start logic
    if args.force_fresh and runner.shadow_mode:
        logger.warning("FORCE-FRESH enabled in shadow mode — bypassing has_open_positions check")
        runner._handle_fresh_start()
    else:
        # Normal flow (will call fresh start only if no positions)
        has_positions = runner.portfolio.has_open_positions()
        logger.info(f"Existing positions detected: {has_positions}")

        if not has_positions:
            runner._handle_fresh_start()
        else:
            logger.info("Takeover scenario — fresh start skipped. "
                        "Use --force-fresh (shadow only) to test basket logic anyway.")

    logger.info("Diagnostic run complete. Review logs above for basket deployment details.")
    logger.info("Expected: attempts logged for every pair in FIXED_UNIVERSE (BTC, ETH, SOL, XRP, DOGE)")


if __name__ == "__main__":
    main()