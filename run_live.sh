#!/bin/bash
set -e
cd /home/brad/projects/crypto-trading-bot
echo "=== PHASE 6 LIVE DEPLOYMENT (11-pair central basket) ==="
echo "Date: $(date)"
echo "Mode: LIVE -- real orders"

# Singleton guard (P2-04 reliability) - prevent duplicate starts (addresses stale pids + multiple manual starts)
if pgrep -f "phase6.core.phase6_runner" > /dev/null 2>&1; then
  existing=$(pgrep -f "phase6.core.phase6_runner" | tr '\n' ' ')
  echo "ERROR: Phase 6 Runner(s) already running (PIDs: $existing). Aborting to avoid dups."
  echo "To force stop extras: pkill -f 'phase6.core.phase6_runner' ; rm -f logs/phase6_runner.pid phase6_live.pid 2>/dev/null || true"
  exit 1
fi

PYTHONPATH=. python -m phase6.core.phase6_runner --config config/trading_config_phase6.json --mode live --confirm-live
echo "Live runner exited."
# P2-04a: Log rotation
LOGFILE="logs/phase6_runner_error.log"
if [ -f "$LOGFILE" ] && [ $(stat -c%s "$LOGFILE") -gt 10485760 ]; then
  mv "$LOGFILE" "${LOGFILE}.old"
  echo "Rotated large log file" >> "${LOGFILE}.old"
fi
