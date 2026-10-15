#!/usr/bin/env bash
# Bank/trail-while-green Sunday review — rebuild CF + decision packet.
# stdout is injected into the Hermes agent prompt (must be non-empty).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
PYTHON="${ROOT}/.venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p logs
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/bank_trail_while_green_sunday_${TS}.log"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

{
  echo "bank_trail_while_green_sunday start ${TS}"
  "$PYTHON" scripts/phase6/run_bank_trail_while_green_sunday_review.py --since 2026-08-06T00:00:00+00:00
  echo "bank_trail_while_green_sunday end"
} >>"$LOG" 2>&1

# Optional pure card (no_agent fallback)
if [[ "${1:-}" == "--tg-card" || "${BANK_TRAIL_SUNDAY_TG_CARD:-0}" == "1" ]]; then
  "$PYTHON" scripts/phase6/run_bank_trail_while_green_sunday_review.py --load-latest --tg-card 2>>"$LOG"
  exit 0
fi

# Default: re-print fact pack header from latest (agent inject)
"$PYTHON" scripts/phase6/run_bank_trail_while_green_sunday_review.py --load-latest --no-write 2>>"$LOG"
