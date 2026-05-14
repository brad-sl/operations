#!/bin/bash
# Phase 5 Health Check (5-min cron)
# Verifies bot + Prometheus running; alerts if down; auto-restarts if needed

BOT_NAME="phase5_multi_pair"
PROMETHEUS_PORT="8502"
LOG_DIR="/home/brad/.openclaw/workspace/operations/crypto-bot/logs"
ALERT_LOG="$LOG_DIR/health_check_alerts.log"

# Create log dir
mkdir -p "$LOG_DIR"

# Check if bot running
if ! ps aux | grep -q "[p]hase5_multi_pair"; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ❌ ALERT: Phase 5 bot NOT running. Auto-restarting..." >> "$ALERT_LOG"
    cd /home/brad/.openclaw/workspace/operations/crypto-bot
    source venv/bin/activate
    nohup python3 phase5_multi_pair.py --cycles 288 > "$LOG_DIR/phase5_live_restart_$(date +%s).log" 2>&1 &
fi

# Check if Prometheus UP
if ! curl -s http://localhost:$PROMETHEUS_PORT/metrics > /dev/null 2>&1; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  WARNING: Prometheus DOWN on :$PROMETHEUS_PORT" >> "$ALERT_LOG"
fi

# Check log freshness (should have new entries within 5 min)
LATEST_LOG=$(ls -t "$LOG_DIR"/phase5_live*.log 2>/dev/null | head -1)
if [ ! -z "$LATEST_LOG" ]; then
    LAST_MOD=$(stat -c %Y "$LATEST_LOG")
    NOW=$(date +%s)
    AGE=$((NOW - LAST_MOD))
    if [ $AGE -gt 600 ]; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  WARNING: No log activity in $AGE seconds" >> "$ALERT_LOG"
    fi
fi

exit 0
