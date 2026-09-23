#!/usr/bin/env bash
# Jev select-few CF weekly rollup — short TG card on stdout. Measure-only.
set -euo pipefail
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
mkdir -p logs/jev_select_few_cf
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/jev_select_few_cf/weekly_${TS}.log"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# stderr → log; stdout = TG card only
{
  echo "jev_select_few_cf_weekly start ${TS}"
  "$ROOT/.venv/bin/python3" scripts/phase6/run_jev_select_few_cf.py --weekly
  echo "jev_select_few_cf_weekly end"
} >>"$LOG" 2>&1
# Deliver card (also append to log)
"$ROOT/.venv/bin/python3" scripts/phase6/run_jev_select_few_cf.py --weekly --no-write 2>>"$LOG" | tee -a "$LOG"
