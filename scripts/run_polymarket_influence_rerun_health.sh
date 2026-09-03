#!/usr/bin/env bash
# Quiet health for ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902
# Empty stdout when OK; alert lines only on fail (Hermes no_agent).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONPATH="${PYTHONPATH:-.}"
exec .venv/bin/python3 phase6/research/run_polymarket_influence_health.py
