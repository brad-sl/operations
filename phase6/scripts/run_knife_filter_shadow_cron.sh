#!/usr/bin/env bash
# Quiet cron — knife filter shadow R1 (measure only).
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT"
LOG_DIR="$ROOT/logs/knife_filter_shadow"
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/${TS}.log"
OUT=$("$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_knife_filter_shadow.py" --tg 2>&1 | tee -a "$LOG")
# always print short line for no_agent TG (low noise)
echo "$OUT"
