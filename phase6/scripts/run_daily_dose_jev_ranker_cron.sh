#!/usr/bin/env bash
# Shadow Daily Dose Jev ranker — local log only, no TG body.
# Does not replace daily-dose-telegram pipeline.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot || exit 1
PY="${PWD}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
mkdir -p logs/daily_dose_jev
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/daily_dose_jev/${STAMP}.log"
{
  echo "=== daily_dose_jev_ranker ${STAMP} ==="
  "$PY" scripts/phase6/run_daily_dose_jev_ranker.py --top 5 --max-judge 16
  echo "--- compare head ---"
  head -n 40 data/state/daily_dose_jev_compare.md 2>/dev/null || true
} | tee "$LOG"
# Quiet success line for no_agent local delivery (optional)
echo "DoseJev shadow done → data/state/daily_dose_jev_compare.md (log $LOG)"
