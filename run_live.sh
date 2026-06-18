#!/bin/bash
# Live Deployment Runner for Phase 6 (Old-style permissive_deploy via deploy_capital - wired primary per diagnostics)
# 
# PRE-REQUISITES (do these first):
# 1. Paper trade chain test passed (full validation of new code + dashboard).
# 2. Config has "use_new_allocator": false and "rebalance_style": "permissive_deploy" (old-style wired).
# 3. You have explicitly decided to go live.
#
# USAGE:
#   bash run_live.sh
#
# This will run the Phase6Runner in LIVE mode (real orders).
# Safety: --confirm-live is REQUIRED. Runner itself will error without it.
#
# Dashboard will be fed automatically with old-style deploy_capital decisions.
# Full chain: signals -> deploy_capital -> execution -> dashboard cache.
#
# Monitor: After start, tail logs and check data/state/phase6_live_state.json
#
# To stop: Ctrl-C (runner is designed for manual or cron control).

set -e

cd /home/brad/projects/crypto-trading-bot

echo "=== PHASE 6 LIVE DEPLOYMENT ==="
echo "Date: $(date)"
echo "Strategy: permissive_deploy (old-style deploy_capital, rebalance_cap_usd=150, edge demonstrated in 365d diagnostics)"
echo "Config: config/trading_config_phase6.json (use_new_allocator=false, rebalance_style=permissive_deploy)"
echo "Mode: LIVE (real capital movement)"
echo ""
echo "CRITICAL: This will place REAL orders on the exchange."
echo "Paper test passed on 2026-06-15. Proceeding only because you requested live deployment."
echo ""

# Explicit system check (per user requirements)
echo "System crontab check (no overlapping trading crons expected):"
crontab -l 2>/dev/null | grep -E "(phase6|rebalance|trading)" || echo "  (No direct phase6 trading crons found - good)"
echo ""

# Run with full safety flags
# Use -m for proper package context so relative imports (from .xxx) succeed
echo "Starting live runner (using -m for package-relative imports)..."
PYTHONPATH=. python -m phase6.core.phase6_runner \\
    --config config/trading_config_phase6.json \\
    --mode live \\
    --confirm-live

echo "Live runner exited."