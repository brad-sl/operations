#!/usr/bin/env bash
# REGIME-CASH continuous (detect → status → knob map → sweep → learnings)
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT"
exec .venv/bin/python3 phase6/research/run_regime_cash_continuous.py
