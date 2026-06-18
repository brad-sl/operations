#!/bin/bash
# Phase 6 Live Rebalance Launcher (Canonical - Post Fable5 + Live Readiness)
# Sources Hermes .env for keys then runs the updated canonical runner with safety flags.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot

# Load keys from Hermes default profile
if [ -f "$HOME/.hermes/.env" ]; then
    set -a
    source "$HOME/.hermes/.env"
    set +a
    echo "[phase6-live] Sourced $HOME/.hermes/.env (keys for Coinbase/OpenRouter)"
fi

# Fallback Hermes config
if command -v hermes >/dev/null 2>&1; then
    HERMES_ENV=$(hermes config env-path 2>/dev/null || true)
    if [ -n "$HERMES_ENV" ] && [ -f "$HERMES_ENV" ]; then
        set -a
        source "$HERMES_ENV"
        set +a
    fi
fi

echo "[phase6-live] Starting canonical Phase 6 runner in LIVE mode at $(date)"
python3 -m phase6.core.phase6_runner \
  --config config/trading_config_phase6.json \
  --mode live \
  --confirm-live
