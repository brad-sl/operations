#!/usr/bin/env bash
# Quiet measure cron: climate vs weather board. Never touches live knobs.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
LOG_DIR="$ROOT/logs/regime_climate_weather"
mkdir -p "$LOG_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/${STAMP}.log"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
{
  echo "=== regime_climate_weather ${STAMP} ==="
  "$PY" scripts/phase6/run_regime_climate_weather.py --tg
  echo "---"
  "$PY" scripts/phase6/run_regime_climate_weather.py 2>&1 | tail -n 40
} | tee "$LOG"
# Full report stays on disk; short card is stdout for Hermes deliver when configured.
exit 0
