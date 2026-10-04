#!/usr/bin/env bash
# Rebuild analyst weekly 7d trade-review fact pack (measure-only).
# Used by Sunday agent cron as prerequisite; also safe standalone.
# stderr → log; optional stdout TG card with --tg-card
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
PYTHON="${ROOT}/.venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p logs
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/analyst_weekly_trade_review_${TS}.log"
{
  echo "analyst_weekly_trade_review start ${TS}"
  "$PYTHON" scripts/phase6/run_analyst_weekly_trade_review.py --days 7
  echo "analyst_weekly_trade_review end"
} >>"$LOG" 2>&1
# Default: silent (agent will compose TG). Pass --tg-card for no_agent fallback card.
if [[ "${1:-}" == "--tg-card" ]]; then
  "$PYTHON" scripts/phase6/run_analyst_weekly_trade_review.py --load-latest --tg-card 2>>"$LOG"
fi
