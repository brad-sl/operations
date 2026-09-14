#!/usr/bin/env bash
# Hermes no_agent: phase6-platform-metrics-spine
# Daily spine refresh. Stdout empty unless --tg (short board only). Full → logs + reports.
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

mkdir -p logs/platform_metrics_spine
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="logs/platform_metrics_spine/${STAMP}.log"

TG=0
if [[ "${1:-}" == "--tg" ]]; then TG=1; fi

{
  echo "# platform-metrics-spine $STAMP"
  "$PY" scripts/phase6/run_platform_metrics_spine.py
} >"$LOG" 2>&1
cp -f "$LOG" logs/platform_metrics_spine/latest.log

if [[ "$TG" -eq 1 ]]; then
  "$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/state/platform_metrics_spine_latest.json")
if not p.exists():
    raise SystemExit(0)
d = json.loads(p.read_text())
go = d.get("go_nogo") or {}
fun = (d.get("lifecycle") or {}).get("funnel") or {}
ch = (d.get("lifecycle") or {}).get("choke_point") or {}
print("platform-metrics-spine")
print(f"ops={go.get('ops')} money={go.get('money_path')} auto={go.get('auto_membership')}")
print(
    f"seat={fun.get('n_seated')}→sig={fun.get('n_signaled')}→fill={fun.get('n_filled')}→win={fun.get('n_filled_win')} "
    f"choke={ch.get('id')}"
)
print(go.get("plain_english") or "")
print("Full: reports/PLATFORM_METRICS_SPINE_LATEST.md")
PY
fi
# default: empty stdout = silent TG delivery
