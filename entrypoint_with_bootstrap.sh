#!/bin/bash
# Enhanced entrypoint with optional bootstrap phase
# Usage:
#   docker compose up              (runs bot normally)
#   docker compose run --rm bot bash entrypoint_with_bootstrap.sh bootstrap
#   docker compose run --rm bot bash entrypoint_with_bootstrap.sh bot

set -e

MODE=${1:-bot}  # Default: run bot. Arg: bootstrap or bot

cd /app

case "$MODE" in
    bootstrap)
        echo "🔥 Generating RSI warm-start bootstrap..."
        python3 bootstrap_rsi_history.py
        echo "✅ Bootstrap complete. Run 'docker compose up' to start bot with warm RSI."
        ;;
    
    bot)
        echo "🤖 Starting Phase 5 Trading Bot..."
        python3 phase5_multi_pair.py --cycles 288
        ;;
    
    *)
        echo "Unknown mode: $MODE"
        echo "Usage: $0 [bootstrap|bot]"
        exit 1
        ;;
esac
