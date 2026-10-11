#!/usr/bin/env bash
# Shadow plain-language Daily Dose notes (post-selection).
# After 08:00 publish freeze (+ optional A/B). Does NOT replace live TG dose.
# Stdout = Telegram body (linked titles + fact paragraphs + one footer).
# Empty stdout when freeze missing → silent TG.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

LOG_DIR="${ROOT}/logs/daily_dose_novice_summary"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="${LOG_DIR}/${TS}.log"

if [[ ! -f data/state/daily_dose_edited.json ]]; then
  echo "PlainSummary skip: no daily_dose_edited.json yet" >>"$LOG"
  exit 0
fi

set +e
"$PY" scripts/phase6/run_daily_dose_novice_summary.py \
  --live --held --top 5 --print-post \
  >"${LOG}.out" 2>"${LOG}.err"
rc=$?
set -e
cat "${LOG}.out" "${LOG}.err" >>"$LOG" || true
if [[ $rc -ne 0 ]]; then
  echo "PlainSummary FAIL rc=$rc" >&2
  tail -n 40 "$LOG" >&2 || true
  exit $rc
fi

# TG body only on stdout
cat "${LOG}.out"
