#!/bin/bash
# Restart Phase 6 live dashboard (reload serve_dashboard.py code).
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT="${DASHBOARD_PORT:-8502}"
PIDFILE="logs/dashboard_${PORT}.pid"

dashboard_pids() {
  ps -eo pid=,args= 2>/dev/null | grep -E "[p]ython(3)?.*serve_dashboard\.py.*--port ${PORT}" | awk '{print $1}'
}

for pid in $(dashboard_pids); do
  echo "Stopping dashboard PID $pid"
  kill "$pid" 2>/dev/null || true
done
sleep 2
for pid in $(dashboard_pids); do
  kill -9 "$pid" 2>/dev/null || true
done
rm -f "$PIDFILE"
bash scripts/phase6/start_dashboard_live.sh