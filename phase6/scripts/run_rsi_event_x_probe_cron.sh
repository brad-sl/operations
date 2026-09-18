#!/usr/bin/env bash
# Quiet RSI-event X probe cron wrapper.
# Default DRY (no paid X). Set PROBE_GO=1 or pass --go to spend under budget.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PY="${PYTHON:-python3}"
ARGS=(scripts/phase6/run_rsi_event_x_probe.py --telegram --quiet-ok)
if [[ "${PROBE_GO:-0}" == "1" ]] || [[ "${1:-}" == "--go" ]]; then
  ARGS+=(--go)
  shift || true
fi
exec "$PY" "${ARGS[@]}" "$@"
