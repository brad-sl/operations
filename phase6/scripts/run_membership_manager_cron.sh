#!/usr/bin/env bash
# Membership Manager tick (self-regulating seats). Brad GO 2026-10-03.
# Seat eligibility only — no orders / no force rebalance / dual_agree still manual.
# Kill: touch data/state/membership_manager_KILL
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONUNBUFFERED=1

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" data/state
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/membership_manager_${TS}.log"
LATEST="$LOG_DIR/membership_manager_latest.log"

set +e
OUT="$(python scripts/phase6/run_membership_manager.py --telegram 2>&1)"
RC=$?
set -e
printf '%s\n' "$OUT" | tee "$LOG" >"$LATEST"

# Print TG body only when manager emitted ---TELEGRAM--- with non-silent content
if printf '%s\n' "$OUT" | grep -q '^---TELEGRAM---$'; then
  MSG="$(printf '%s\n' "$OUT" | awk 'f&&!/^\(silent\)$/{print} /^---TELEGRAM---$/{f=1}')"
  if [[ -n "${MSG// }" && "$MSG" != "(silent)" ]]; then
    printf '%s\n' "$MSG"
  fi
fi
exit "$RC"
