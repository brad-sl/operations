#!/usr/bin/env bash
# Jev select-few CF — measure-only. Local deliver by default (cron); --tg for card.
set -euo pipefail
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
mkdir -p logs/jev_select_few_cf
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/jev_select_few_cf/${TS}.log"
if [[ -f /home/brad/.hermes/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /home/brad/.hermes/.env
  set +a
fi
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
{
  echo "jev_select_few_cf start ${TS}"
  "$ROOT/.venv/bin/python3" scripts/phase6/run_jev_select_few_cf.py "$@"
  echo "jev_select_few_cf end"
} >>"$LOG" 2>&1
# Quiet success: empty stdout unless JEV_CF_TG=1
if [[ "${JEV_CF_TG:-}" == "1" ]]; then
  "$ROOT/.venv/bin/python3" scripts/phase6/run_jev_select_few_cf.py --tg --no-write --no-refresh-ohlcv
fi
