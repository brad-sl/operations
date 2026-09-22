#!/usr/bin/env bash
# Locked-pool Daily Dose A/B — after 08:00 publish freeze exists.
# Shadow only. Live dose unchanged.
# deliver=telegram → stdout = short A/B card only (logs on file).
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
  echo "DoseAB skip: no daily_dose_edited.json yet" >>"$LOG"
  # empty stdout = silent TG (nothing to compare yet)
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

# Short operator card only on stdout (Hermes deliver=telegram)
# Prefer cached latest (no second Jev burn); rebuild card text from JSON.
"$PY" - <<'PY'
from pathlib import Path
import json
import sys
sys.path.insert(0, ".")
from phase6.core.daily_dose_jev_ab import format_tg_card
p = Path("data/state/daily_dose_jev_ab_latest.json")
if not p.is_file():
    raise SystemExit(0)
payload = json.loads(p.read_text(encoding="utf-8"))
print(format_tg_card(payload))
PY
