#!/bin/bash
# Start Phase 6 live dashboard (port 8502) — singleton + pidfile (mirrors start_phase6_runner.sh)
set -euo pipefail

cd "$(dirname "$0")/../.."
mkdir -p logs

PORT="${DASHBOARD_PORT:-8502}"
PIDFILE="logs/dashboard_${PORT}.pid"
LOG="logs/dashboard_${PORT}.log"

dashboard_pids() {
  ps -eo pid=,args= 2>/dev/null | grep -E "[p]ython(3)?.*serve_dashboard\\.py.*--port ${PORT}" | awk '{print $1}'
}

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null || echo 0)
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "ERROR: Dashboard already running per pidfile (PID: $OLD_PID, port $PORT). Aborting."
    exit 1
  fi
  echo "Stale dashboard pidfile for $OLD_PID; removing."
  rm -f "$PIDFILE"
fi

existing=$(dashboard_pids | tr '\n' ' ')
if [ -n "$existing" ]; then
  echo "ERROR: Dashboard already running (PIDs: $existing, port $PORT). Aborting."
  exit 1
fi

PYTHON="${PWD}/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

echo "Starting live dashboard on port $PORT..."
nohup "$PYTHON" serve_dashboard.py --port "$PORT" --mode live >> "$LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PIDFILE"
sleep 1
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "Dashboard started PID $NEW_PID — http://0.0.0.0:$PORT"
  echo "Log: $LOG"
else
  echo "ERROR: Dashboard failed to stay up; see $LOG"
  rm -f "$PIDFILE"
  exit 1
fi