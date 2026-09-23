#!/usr/bin/env bash
# Quiet cron wrapper: break-even one-pager → short TG card on stdout.
set -euo pipefail
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
mkdir -p logs/break_even_one_pager
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/break_even_one_pager/${TS}.log"
# shellcheck disable=SC2094
{
  echo "break_even_one_pager start ${TS}"
  PYTHONPATH=. "$ROOT/.venv/bin/python3" scripts/phase6/run_break_even_one_pager.py \
    --week-start 2026-09-23 --be 150 --x-week 25 "$@"
  echo "break_even_one_pager end"
} >>"$LOG" 2>&1
# stdout for Hermes deliver = TG card only
PYTHONPATH=. "$ROOT/.venv/bin/python3" scripts/phase6/run_break_even_one_pager.py \
  --tg --week-start 2026-09-23 --be 150 --x-week 25 --no-write
