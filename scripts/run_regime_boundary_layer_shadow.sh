#!/usr/bin/env bash
# Hermes cron entrypoint — boundary layer cream shadow (no live orders).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi
exec "$PY" phase6/research/run_regime_boundary_layer_shadow.py
