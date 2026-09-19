#!/usr/bin/env bash
# Trial closeout watchdog — TG only when a trial needs Brad decide.
# Full board always on disk. No auto-decide / no live knobs.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
export PYTHONPATH="${PYTHONPATH:-.}"
mkdir -p logs/trial_closeout_watch
ts=$(date -u +%Y%m%dT%H%M%SZ)
log="logs/trial_closeout_watch/${ts}.log"
set +e
.venv/bin/python3 phase6/research/trial_closeout_watch.py --deliver >"/tmp/trial_closeout_watch_out.txt" 2>>"$log"
set -e
cat "/tmp/trial_closeout_watch_out.txt" >>"$log" 2>/dev/null || true
if [[ -s /tmp/trial_closeout_watch_out.txt ]]; then
  cat /tmp/trial_closeout_watch_out.txt
fi
exit 0
