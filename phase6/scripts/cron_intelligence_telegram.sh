#!/bin/bash
# Twice-daily crypto-analyst intelligence → Telegram
# Hermes cron job twice-daily-trading-intelligence-v2 (c16b620103dc):
#   no_agent=true + deliver=telegram → THIS SCRIPT'S STDOUT is the TG body.
# Do NOT pipe to `hermes send` here (cron PATH often lacks ~/.local/bin; double-send risk).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"

cd /home/brad/projects/crypto-trading-bot || exit 1
PYTHON="${PWD}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

mkdir -p logs
LOG="logs/intelligence_cron.log"
# stderr → log (library INFO noise); clean brief on stdout for TG delivery
exec "$PYTHON" phase6/scripts/generate_trading_intelligence_report.py 2>>"$LOG"
