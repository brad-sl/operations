#!/usr/bin/env bash
# Shadow Daily Dose Jev ranker.
# Does NOT replace daily-dose-telegram live dose.
# deliver=telegram → stdout = short shadow brief only (logs on file).
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
} >>"$LOG" 2>&1

# Telegram body = preview only (shadow · not a trade signal · not live dose)
if [[ -f data/state/daily_dose_jev_preview.txt ]]; then
  cat data/state/daily_dose_jev_preview.txt
else
  echo "DoseJev shadow: no preview yet (see $LOG)" >&2
fi
