#!/usr/bin/env bash
# Backfill Phase 6 runner PID files when the process was started outside start_phase6_runner.sh
set -euo pipefail
ROOT="${1:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
PID="$(pgrep -f 'python.* -m phase6\.core\.phase6_runner' | head -1 || true)"
if [ -z "$PID" ]; then
  echo "[sync_runner_pid] no phase6_runner process found"
  exit 1
fi
mkdir -p logs data/state
echo "$PID" > logs/phase6_runner.pid
echo "$PID" > data/state/phase6_runner.pid
echo "[sync_runner_pid] wrote PID $PID to logs/ and data/state/"
exit 0