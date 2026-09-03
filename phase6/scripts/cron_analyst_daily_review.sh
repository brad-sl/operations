#!/usr/bin/env bash
# Hermes no_agent: Analyst Daily Review → Telegram when material.
# stdout = TG body; empty stdout = silent (no filler).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
PYTHON="${ROOT}/.venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p logs
# stderr → log; stdout only for TG
exec "$PYTHON" phase6/research/run_analyst_daily_review.py --deliver 2>>logs/analyst_daily_review.log
