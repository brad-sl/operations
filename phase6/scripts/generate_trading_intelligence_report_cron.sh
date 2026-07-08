#!/bin/bash
# Thin launcher for Hermes no_agent cron (Phase6 Intelligence Brief)
# Used by both "Phase6 Deep Maintenance Brief" (0 3 * * *) and "Phase6 Pre-Rebalance Intelligence Brief" (30 8,20 * * *)
# Enforces canonical project root + correct __file__ for the bootstrap in generate_trading_intelligence_report.py
# per DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py
cd /home/brad/projects/crypto-trading-bot || exit 1
exec python3 phase6/scripts/generate_trading_intelligence_report.py
