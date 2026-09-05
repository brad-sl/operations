#!/usr/bin/env bash
# TCS shadow would-block + CF refresh (Hermes no_agent cron).
# Paper/shadow only — no orders, no evaluate_buy_entry blocks, no config writes.
# stdout empty on success (deliver=local). FAIL line on error for cron history.
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.local/bin:${PATH}"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data/state" "$ROOT/reports"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/tcs_shadow_would_block_${TS}.log"
LATEST_LOG="$LOG_DIR/tcs_shadow_would_block_latest.log"

set +e
{
  echo "=== TCS shadow $(date -u -Iseconds) ==="
  python phase6/research/run_trade_comparison_cf.py
  echo "---"
  python phase6/research/run_tcs_shadow_would_block.py
  echo "=== done rc=$? ==="
} >"$LOG" 2>&1
RC=$?
set -e
cp -f "$LOG" "$LATEST_LOG"

if [[ "$RC" -ne 0 ]]; then
  # Non-empty stdout → can surface if failure_deliver is set; else cron history only
  echo "TCS shadow FAILED rc=$RC log=$LATEST_LOG"
  exit "$RC"
fi
# success: empty stdout (local deliver = silent)
exit 0
