#!/bin/bash
set -euo pipefail

ROOT_DIR="/home/brad/.openclaw/workspace/operations/crypto-bot"
CDIR="$ROOT_DIR"
VENV_BIN="$ROOT_DIR/venv/bin/python3"
SCRIPT="$ROOT_DIR/phase4b_v1.py"
LOG="$ROOT_DIR/phase4b_48h_run.log"
PID_FILE="$ROOT_DIR/phase4b.pid"

start() {
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if ps -p "$pid" > /dev/null 2>&1; then
      echo "[$(date)] Phase4b already running (PID $pid)" >> "$LOG"
      return 0
    else
      echo "[$(date)] Stale PID file found. Cleaning up." >> "$LOG"
      rm -f "$PID_FILE"
    fi
  fi

  echo "[$(date)] Starting Phase4b..." >> "$LOG"
  nohup "$VENV_BIN" "$SCRIPT" >> "$LOG" 2>&1 &
  echo $! > "$PID_FILE"
  echo "[$(date)] Started Phase4b (PID $(cat "$PID_FILE"))" >> "$LOG"
}

monitor() {
  while true; do
    if [ -f "$PID_FILE" ]; then
      pid=$(cat "$PID_FILE")
      if ps -p "$pid" > /dev/null 2>&1; then
        sleep 60
        continue
      else
        echo "[$(date)] Phase4b process not running. Restarting..." >> "$LOG"
      fi
    else
      echo "[$(date)] No PID file. Starting Phase4b..." >> "$LOG"
    fi

    start
    sleep 10
  done
}

echo "[$(date)] Phase4b supervisor starting..." >> "$LOG"
cd "$CDIR"
start
monitor
