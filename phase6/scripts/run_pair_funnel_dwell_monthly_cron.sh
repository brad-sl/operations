#!/usr/bin/env bash
# Monthly pair-funnel dwell summary — measure-only TG table.
# Pair × stage visit counts. No prediction. No money path.
set -euo pipefail
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
mkdir -p logs/pair_funnel_dwell
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/pair_funnel_dwell/monthly_${TS}.log"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="$ROOT/.venv/bin/python3"
# stderr → log; stdout = TG card only (Hermes no_agent deliver)
{
  echo "pair_funnel_dwell_monthly start ${TS}"
  "$PY" scripts/phase6/run_pair_funnel_dwell.py --monthly
  echo "pair_funnel_dwell_monthly end"
} >>"$LOG" 2>&1
# Re-print card to stdout for delivery (also tee log)
"$PY" scripts/phase6/run_pair_funnel_dwell.py --monthly --no-write 2>>"$LOG" | tee -a "$LOG"
