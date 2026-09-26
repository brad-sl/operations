#!/usr/bin/env bash
# Post-15m-RSI tryout seat: scan regime doors + quiet TG approval when dual-clear.
# Money OFF until Brad GO (approval ladder) or policy auto_armed.
# Quiet: empty stdout when nothing to approve (Hermes deliver=telegram stays silent).
set -euo pipefail
ROOT="${PHASE6_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONPATH=.
PY="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PY="$ROOT/.venv/bin/python3"
fi

GO_X="${COMPOSER_GO_X:-1}"
FORCE=0
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --go-x) GO_X=1 ;;
    --no-x) GO_X=0 ;;
    --force) FORCE=1 ;;
    *) EXTRA+=("$arg") ;;
  esac
done

LOG_DIR="$ROOT/logs/rsi_event_tryout_seat"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/${TS}.log"

ARGS=(scripts/phase6/run_rsi_event_tryout_seat_composer.py --post-rsi --quiet-ok)
if [[ "$GO_X" == "1" ]]; then
  ARGS+=(--go-x)
fi

# Always log full JSON
{
  echo "=== rsi_event_tryout_seat ${TS} ==="
  "$PY" "${ARGS[@]}" --json "${EXTRA[@]}"
} >>"$LOG" 2>&1 || {
  echo "TRYOUT SEAT composer failed — see $LOG" >&2
  exit 1
}

# Stdout = approval card only (or empty). --force re-sends same fingerprint.
"$PY" - "$FORCE" <<'PY' 2>>"$LOG"
import json, sys
from pathlib import Path
from phase6.core.paths import STATE_DIR
from phase6.core.rsi_event_tryout_seat_composer import approval_stdout
from phase6.core.rsi_event_tryout_seat_policy import approval_telegram_card

force = str(sys.argv[1] if len(sys.argv) > 1 else "0") == "1"
p = STATE_DIR / "rsi_event_tryout_seat_composer_latest.json"
if not p.exists():
    raise SystemExit(0)
payload = json.loads(p.read_text())
if force:
    card = approval_telegram_card(payload, force=True, mark_sent=True)
else:
    card = payload.get("approval_card") or approval_stdout(payload, force=False)
if card:
    print(card)
PY
exit 0
