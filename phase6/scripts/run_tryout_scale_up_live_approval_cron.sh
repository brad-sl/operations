#!/usr/bin/env bash
# Tryout scale-up LIVE approval ping — plan only, never money.
# TG body only when armed + n_planned>0; else empty stdout (quiet no_agent).
# Same fingerprint ≤12h stays silent (see approval_seen.json).
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONPATH=.
LOG_DIR="$ROOT/logs/tryout_scale_up_live_approval"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/${TS}.log"

# Log full plan JSON (always)
{
  echo "=== tryout_scale_up_live_approval ${TS} ==="
  ./.venv/bin/python3 scripts/phase6/run_tryout_scale_up_live_approval.py --json
} >>"$LOG" 2>&1 || {
  echo "SCALE-UP APPROVAL plan failed — see $LOG" >&2
  exit 1
}

# Stdout = approval card or empty (dedupe applies; no --force)
./.venv/bin/python3 scripts/phase6/run_tryout_scale_up_live_approval.py 2>>"$LOG"
exit 0
