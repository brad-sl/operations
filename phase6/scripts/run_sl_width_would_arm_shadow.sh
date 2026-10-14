#!/usr/bin/env bash
# 3% SL fuse would-arm shadow (MEASURE_ONLY). Always non-empty stdout.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec "$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_sl_width_would_arm_shadow.py"
