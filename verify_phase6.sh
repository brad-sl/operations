#!/bin/bash
# Phase 6 Verification Script
# Runs bot for 5 minutes (reduced for test)

set -e

echo "🚀 Phase 6 Trading Bot Verification (Trial)"
echo "===================================="

# Check config
CONFIG="config/trading_config_phase6.json"
if [ ! -f "$CONFIG" ]; then
    echo "❌ Config not found: $CONFIG"
    exit 1
fi
echo "✅ Config found: $CONFIG"

# Start bot
echo ""
echo "🔄 Starting Phase 6 Trading Bot..."
echo "   Config: $CONFIG"
echo "   Mode: shadow"
echo "   Duration: 5 minutes (test)"
echo ""

export PYTHONPATH=.
python3 -m phase6.core.phase6_runner --config "$CONFIG" --mode shadow &
BOT_PID=$!

echo "✅ Bot started (PID: $BOT_PID)"

# Monitor
echo "📊 Monitoring bot for 5 minutes..."
DURATION=300
ELAPSED=0
CHECK_INTERVAL=10

while [ $ELAPSED -lt $DURATION ]; do
    sleep $CHECK_INTERVAL
    
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "❌ Bot crashed!"
        exit 1
    fi
    
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))
    PROGRESS=$((ELAPSED * 100 / DURATION))
    echo "⏳ Running: ${PROGRESS}% (${ELAPSED}s / ${DURATION}s)"
done

echo ""
echo "✅ Bot ran continuously for 5 minutes!"

# Kill bot gracefully
echo "🛑 Stopping bot..."
kill $BOT_PID 2>/dev/null || true
wait $BOT_PID 2>/dev/null || true

echo "✨ Phase 6 Verification Complete!"
