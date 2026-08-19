#!/usr/bin/env bash
# Weekly SL vs shadow-exit counterfactual → stdout (Hermes no_agent / Telegram).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PYTHON="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi
exec "$PYTHON" "$ROOT/scripts/phase6/sl_exit_counterfactual_report.py" "$@"
