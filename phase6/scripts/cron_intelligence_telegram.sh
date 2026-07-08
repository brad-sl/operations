#!/bin/bash
# Twice-daily crypto-analyst intelligence → Telegram (Linux crontab launcher)
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot || exit 1
PYTHON="${PWD}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi
# Hermes CLI: use `hermes send -t telegram` (stdin). NOT --target/--message (removed).
"$PYTHON" phase6/scripts/generate_trading_intelligence_report.py 2>&1 | hermes send -t telegram