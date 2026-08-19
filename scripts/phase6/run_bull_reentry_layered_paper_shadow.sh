#!/usr/bin/env bash
# Thin wrapper — paper shadow layered re-entry (no live knobs).
set -euo pipefail
export OPENBLAS_CORETYPE=GENERIC
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
exec "$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_bull_reentry_layered_paper_shadow.py"
