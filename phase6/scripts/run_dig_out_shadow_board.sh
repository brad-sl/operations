#!/usr/bin/env bash
# Dig-out shadow board (C1/D1/B/W2 measure-only). Always non-empty stdout for Hermes no_agent.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec "$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_dig_out_shadow_board.py" --quiet-ok
