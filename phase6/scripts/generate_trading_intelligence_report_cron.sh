#!/usr/bin/env bash
# Hermes no_agent: Deep Maintenance + Pre-Rebalance intelligence briefs.
# Always runs project tree with venv (never stale ~/.hermes script copies of the .py).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi
exec "$PY" phase6/scripts/generate_trading_intelligence_report.py
