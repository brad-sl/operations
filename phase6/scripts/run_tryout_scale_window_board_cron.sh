#!/usr/bin/env bash
# Scale-window board cron: evaluate + quiet TG when n_would_eject>0.
# NEVER places orders. live_apply stays config-gated (default OFF).
# Quiet: empty stdout when nothing to eject / same 12h fingerprint.
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH=.
PY="${ROOT}/.venv/bin/python3"
[[ -x "$PY" ]] || { echo "scale-window board: missing venv python at $PY" >&2; exit 1; }

LOG_DIR="${ROOT}/logs/tryout_scale_window"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="${LOG_DIR}/board_${TS}.log"

# Always refresh board JSON on disk; TG body only when would_eject + new fp.
set +e
"$PY" scripts/phase6/run_tryout_scale_window.py --json >"${LOG_DIR}/board_latest.json" 2>>"$LOG"
rc_board=$?
BODY="$("$PY" scripts/phase6/run_tryout_scale_window.py --telegram-board 2>>"$LOG")"
rc_tg=$?
set -e

if [[ $rc_board -ne 0 ]]; then
  echo "scale-window board evaluate failed rc=$rc_board" >&2
  tail -n 40 "$LOG" >&2 || true
  exit "$rc_board"
fi
if [[ $rc_tg -ne 0 ]]; then
  echo "scale-window board telegram failed rc=$rc_tg" >&2
  tail -n 40 "$LOG" >&2 || true
  exit "$rc_tg"
fi

# Empty stdout = silent (Hermes no_agent).
if [[ -n "${BODY// }" ]]; then
  printf '%s\n' "$BODY"
fi
exit 0
