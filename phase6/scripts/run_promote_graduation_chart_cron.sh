#!/usr/bin/env bash
# Hermes no_agent: phase6-promote-graduation-chart (P2)
# After pick-metrics refresh preferred. Measure-only. Short TG board.
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3

mkdir -p logs/promote_graduation_chart
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="logs/promote_graduation_chart/${STAMP}.log"

TG=0
[[ "${1:-}" == "--tg" ]] && TG=1

{
  echo "# promote-graduation-chart $STAMP"
  "$PY" scripts/phase6/run_promote_graduation_chart.py
  # refresh spine so promote_graduation section joins
  "$PY" scripts/phase6/run_platform_metrics_spine.py || true
} >"$LOG" 2>&1
cp -f "$LOG" logs/promote_graduation_chart/latest.log

if [[ "$TG" -eq 1 ]]; then
  "$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/state/promote_graduation_chart_latest.json")
if not p.exists():
    raise SystemExit(0)
d = json.loads(p.read_text())
go = d.get("go_nogo") or {}
fun = d.get("funnel") or {}
ch = d.get("choke_point") or {}
paper = d.get("paper") or {}
print("promote-graduation-chart")
print(f"talk={go.get('promote_talk_ok')} claim={go.get('claim_allowed')} path={go.get('money_path_hint')}")
print(
    f"seat={fun.get('n_seated')}→sig={fun.get('n_signaled')}→fill={fun.get('n_filled')}→win={fun.get('n_filled_win')} "
    f"choke={ch.get('id')}"
)
print(f"paper_hit7={paper.get('hit_rate_positive_7d')} avg7={paper.get('avg_ret_7d_pct')}")
print(go.get("plain_english") or "")
print("Charts: /charts/promote-graduation/funnel.svg")
print("Full: reports/PROMOTE_GRADUATION_CHART_LATEST.md")
PY
fi
