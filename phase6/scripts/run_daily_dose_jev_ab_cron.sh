#!/usr/bin/env bash
# Locked-pool Daily Dose A/B — after 08:00 publish freeze exists.
# Shadow only. Default: log + card on disk. Optional TG short card via DOSE_AB_TG=1.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
LOG_DIR="${ROOT}/logs/daily_dose_jev_ab"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="${LOG_DIR}/${TS}.log"

# Need edited package from today's pipeline
if [[ ! -f data/state/daily_dose_edited.json ]]; then
  echo "DoseAB skip: no daily_dose_edited.json yet" | tee -a "$LOG"
  exit 0
fi

set +e
"$PY" scripts/phase6/run_daily_dose_jev_ab.py --top 5 --max-judge 16 >"${LOG}.out" 2>"${LOG}.err"
rc=$?
set -e
cat "${LOG}.out" "${LOG}.err" >>"$LOG" || true
if [[ $rc -ne 0 ]]; then
  echo "DoseAB FAIL rc=$rc" >&2
  tail -n 40 "$LOG" >&2 || true
  exit $rc
fi

# Quiet success by default (local cron). Opt-in short TG card:
if [[ "${DOSE_AB_TG:-0}" == "1" ]]; then
  "$PY" scripts/phase6/run_daily_dose_jev_ab.py --top 5 --max-judge 16 --print-tg 2>/dev/null \
    | tee -a "$LOG" || true
fi
exit 0
