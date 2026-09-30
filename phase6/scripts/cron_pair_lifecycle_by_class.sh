#!/usr/bin/env bash
# Measure-only class×lifecycle board. Quiet unless broken.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi
exec "$PY" scripts/phase6/run_pair_lifecycle_by_class.py
