#!/usr/bin/env bash
# Evening shell-slot score. Full card on disk. Stdout empty unless fill/bug/RSI-only/final slot.
set -euo pipefail
ROOT=/home/brad/projects/crypto-trading-bot
cd "$ROOT"
export PYTHONPATH=.
LOG_DIR="$ROOT/logs/shell_slot_score"
mkdir -p "$LOG_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PY="$ROOT/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi
"$PY" scripts/phase6/run_shell_slot_score.py --write >"$LOG_DIR/${STAMP}.log" 2>&1
# Telegram body is the only stdout (may be empty)
"$PY" scripts/phase6/run_shell_slot_score.py
