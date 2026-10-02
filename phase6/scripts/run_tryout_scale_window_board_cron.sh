#!/usr/bin/env bash
# Scale-window board cron: evaluate + quiet TG when n_would_eject>0.
# When config live_apply=true and no KILL: auto-eject would_eject shells
# (require_would_eject belt + 48h cooloff). Brad GO 2026-10-01.
# Quiet: empty stdout when nothing to report.
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

# Auto-eject when live_apply armed (Python gates kill + would_eject).
set +e
AUTO_OUT="$("$PY" - <<'PY' 2>>"$LOG"
from phase6.core.tryout_scale_window import auto_eject_if_armed, load_cfg
import json
c = load_cfg()
if not c.get("live_apply"):
    print("")
    raise SystemExit(0)
s = auto_eject_if_armed(dry_run=False)
if not s.get("ran"):
    print("")
    raise SystemExit(0)
n_ok = int(s.get("n_ok") or 0)
n = int(s.get("n") or 0)
pairs = []
for r in s.get("results") or []:
    if isinstance(r, dict) and r.get("success"):
        pairs.append(str(r.get("pair") or ""))
msg = f"SCALE-WINDOW AUTO-EJECT n_ok={n_ok}/{n} pairs={' '.join(pairs) or '-'}"
print(msg)
raise SystemExit(0 if n_ok == n else 1)
PY
)"
rc_auto=$?
set -e

# Prefer auto-eject notice over measure board when both fire.
if [[ -n "${AUTO_OUT// }" ]]; then
  printf '%s\n' "$AUTO_OUT"
  if [[ $rc_auto -ne 0 ]]; then
    echo "scale-window auto-eject partial/fail rc=$rc_auto" >&2
    tail -n 40 "$LOG" >&2 || true
    exit "$rc_auto"
  fi
  exit 0
fi

# Empty stdout = silent (Hermes no_agent).
if [[ -n "${BODY// }" ]]; then
  printf '%s\n' "$BODY"
fi
exit 0
