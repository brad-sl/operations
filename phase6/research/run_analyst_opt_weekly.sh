#!/usr/bin/env bash
# Hermes no_agent cron: ANALYST-OPT weekly (repo canonical — sync to ~/.hermes/scripts/phase6/research/)
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT"
# REGIME-CASH continuous (detect/sweep/learnings; no auto-promote)
.venv/bin/python3 phase6/research/run_regime_cash_continuous.py || true
# Validate live setup vs modeled scorecard window (history jsonl)
.venv/bin/python3 phase6/research/run_regime_cash_validation.py || true
# TREND-REPAIR status for Analyst (no capital moves)
.venv/bin/python3 -m phase6.research.trend_repair || true
exec .venv/bin/python3 phase6/research/run_analyst_opt_weekly.py
