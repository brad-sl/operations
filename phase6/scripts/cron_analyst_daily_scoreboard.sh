#!/usr/bin/env bash
# Hermes no_agent: Analyst daily scoreboard (facts only). Quiet stdout.
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
PYTHON="${ROOT}/.venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p logs
exec "$PYTHON" phase6/research/analyst_daily_scoreboard.py >>logs/analyst_daily_scoreboard.log 2>&1
