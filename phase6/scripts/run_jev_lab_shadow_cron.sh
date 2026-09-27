#!/usr/bin/env bash
# Quiet Jev lab shadow — measure only, no orders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
# load hermes env for OPENROUTER_API_KEY without printing
if [[ -f /home/brad/.hermes/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /home/brad/.hermes/.env
  set +a
fi
PY="$ROOT/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
exec "$PY" scripts/phase6/run_jev_lab_shadow.py --pairs BTC-USD,ETH-USD
