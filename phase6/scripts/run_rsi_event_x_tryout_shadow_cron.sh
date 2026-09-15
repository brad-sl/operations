#!/usr/bin/env bash
# Quiet cron: RSI-event X tryout shadow (measure only; no orders; no paid X).
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
LOG_DIR="$ROOT/logs/rsi_event_x_tryout_shadow"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/${TS}.log"
# Full board to log; Telegram only when top-K non-empty
set +e
"$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_rsi_event_x_tryout_shadow.py" --json >"$LOG" 2>&1
rc=$?
set -e
ln -sfn "$LOG" "$LOG_DIR/latest.log"
if [[ "${1:-}" == "--tg" || "${1:-}" == "--telegram" ]]; then
  "$ROOT/.venv/bin/python3" "$ROOT/scripts/phase6/run_rsi_event_x_tryout_shadow.py" --telegram --quiet-ok || true
fi
exit "$rc"
