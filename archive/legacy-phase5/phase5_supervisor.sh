#!/bin/bash
# Phase 5 Multi-Pair Trading Supervisor
# Maintains Phase 5.1 LIVE + Phase 6 PAPER trading with auto-restart on crash

set -euo pipefail

ROOT_DIR="/home/brad/.openclaw/workspace/operations/crypto-bot"
VENV_BIN="$ROOT_DIR/venv/bin/python3"
SCRIPT="$ROOT_DIR/phase5_multi_pair.py"
LOG_DIR="$ROOT_DIR/logs"
PIDFILE="$ROOT_DIR/phase5_supervisor.pid"

# Create logs dir if needed
mkdir -p "$LOG_DIR"

# Cleanup on exit
trap 'echo "[$(date)] Supervisor shutting down" >> "$LOG_DIR/supervisor.log"; rm -f "$PIDFILE"; exit 0' SIGTERM SIGINT

start_process() {
  local phase=$1
  local logfile=$2
  
  echo "[$(date)] Starting $phase..." >> "$LOG_DIR/supervisor.log"
  nohup "$VENV_BIN" "$SCRIPT" > "$logfile" 2>&1 &
  local pid=$!
  echo "[$(date)] $phase started (PID $pid)" >> "$LOG_DIR/supervisor.log"
  echo $pid
}

# Store supervisor PID
echo $$ > "$PIDFILE"

cd "$ROOT_DIR"

echo "[$(date)] Phase 5 Supervisor started" >> "$LOG_DIR/supervisor.log"

# Start both processes
PID_PHASE5=$(start_process "Phase 5.1 LIVE" "$LOG_DIR/phase5_live.log")
sleep 2
PID_PHASE6=$(start_process "Phase 6 PAPER" "$LOG_DIR/phase6_paper.log")
sleep 2

# Monitor loop
while true; do
  # Check Phase 5.1
  if ! ps -p $PID_PHASE5 > /dev/null 2>&1; then
    echo "[$(date)] Phase 5.1 LIVE crashed or exited. Restarting..." >> "$LOG_DIR/supervisor.log"
    PID_PHASE5=$(start_process "Phase 5.1 LIVE (restart)" "$LOG_DIR/phase5_live.log")
    sleep 2
  fi
  
  # Check Phase 6
  if ! ps -p $PID_PHASE6 > /dev/null 2>&1; then
    echo "[$(date)] Phase 6 PAPER crashed or exited. Restarting..." >> "$LOG_DIR/supervisor.log"
    PID_PHASE6=$(start_process "Phase 6 PAPER (restart)" "$LOG_DIR/phase6_paper.log")
    sleep 2
  fi
  
  sleep 30
done
