#!/bin/bash
# Start Phase 6 Runner in background with logging
# Enhanced with singleton + pidfile validation + log rotation (P2-04 reliability)

cd "$(dirname "$0")/../.."

mkdir -p logs

# Simple log rotation for oversized logs (prevent 50M+ growth)
for LOG in logs/phase6_runner_error.log logs/phase6_runner.log; do
  if [ -f "$LOG" ]; then
    size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    if [ "$size" -gt 10000000 ]; then
      mv "$LOG" "${LOG}.$(date +%Y%m%d-%H%M%S).rotated" 2>/dev/null || true
      echo "Rotated oversized $LOG"
    fi
  fi
done

# Robust singleton using pgrep + pidfile (better than pgrep alone for dups/stales)
PIDFILE=logs/phase6_runner.pid
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null || echo 0)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: Phase 6 Runner already running per pidfile (PID: $OLD_PID). Aborting."
        echo "Current ps runners: $(pgrep -f phase6.core.phase6_runner | tr '\n' ' ')"
        echo "To clean: pkill -f 'phase6.core.phase6_runner' ; rm -f $PIDFILE phase6_live.pid"
        exit 1
    else
        echo "Stale pidfile found for $OLD_PID; removing before start."
        rm -f "$PIDFILE"
    fi
fi

# Also block if any live runner (strict: real python -m launch only; not shell wrappers)
runner_pids() {
  ps -eo pid=,args= 2>/dev/null | grep -E '[p]ython(3)?.* -m phase6\.core\.phase6_runner' | awk '{print $1}'
}
existing_pids=$(runner_pids | tr '\n' ' ')
if [ -n "$existing_pids" ]; then
  echo "ERROR: Phase 6 Runner already running (PIDs: $existing_pids). Aborting to prevent duplicates."
  echo "Use: runner_pids | xargs kill; rm -f $PIDFILE phase6_live.pid"
  exit 1
fi

echo "Starting Phase 6 Runner (singleton checks passed)..."

PYTHON="${PWD}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

nohup "$PYTHON" -m phase6.core.phase6_runner --mode live --confirm-live >> logs/phase6_runner.log 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PIDFILE"

echo "Runner started with PID $(cat $PIDFILE)"
echo "Logs: logs/phase6_runner.log (note: some deploys use phase6_runner_error.log)"
echo "Monitor (15m) and weekly cron will now detect dups and stale pids explicitly."
