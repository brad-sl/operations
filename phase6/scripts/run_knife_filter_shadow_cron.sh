#!/usr/bin/env bash
# Quiet cron — knife filter shadow R1 (measure only).
# Local log only — no Telegram (Brad: ATTENTION_ONLY board is not operator-useful daily).
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT"
LOG_DIR="$ROOT/logs/knife_filter_shadow"
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/${TS}.log"
# Full JSON to log; empty stdout → no_agent delivers nothing even if deliver≠local
"$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_knife_filter_shadow.py" >"$LOG" 2>&1 || {
  echo "knife_filter_shadow FAILED exit=$? — see $LOG" >&2
  exit 1
}
# success: silent
exit 0
