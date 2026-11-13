#!/usr/bin/env bash
# Crash cascade tripwire — 15m continuous monitor (Hermes no_agent).
# Quiet on no-trip (empty stdout). TRIP line or FAIL on stdout.
# Rebalance path still evaluates independently (defense-in-depth).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
mkdir -p logs
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
# Library chatter → log; clean stdout for Hermes deliver=local
exec "$PY" -m phase6.core.crash_cascade_tripwire --tick \
  2>>logs/crash_cascade_tripwire_tick.log
