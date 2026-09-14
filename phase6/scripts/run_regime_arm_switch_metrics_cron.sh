#!/usr/bin/env bash
# Hermes no_agent: phase6-regime-arm-switch-metrics (P3)
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || PY=python3
mkdir -p logs/regime_arm_switch_metrics
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="logs/regime_arm_switch_metrics/${STAMP}.log"
TG=0
[[ "${1:-}" == "--tg" ]] && TG=1
{
  echo "# regime-arm-switch-metrics $STAMP"
  "$PY" scripts/phase6/run_regime_arm_switch_metrics.py
} >"$LOG" 2>&1
cp -f "$LOG" logs/regime_arm_switch_metrics/latest.log
if [[ "$TG" -eq 1 ]]; then
  "$PY" - <<'PY'
from pathlib import Path
import json
p=Path('data/state/regime_arm_switch_metrics_latest.json')
if not p.exists():
    raise SystemExit(0)
from phase6.core.regime_arm_switch_metrics import short_board
print(short_board(json.loads(p.read_text())))
print('Full: reports/REGIME_ARM_SWITCH_METRICS_LATEST.md')
PY
fi
