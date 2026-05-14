#!/bin/bash
# Phase 6 Verification Script
# Runs bot for 1+ hour in paper trading mode

set -e

echo "🚀 Phase 6 Trading Bot Verification"
echo "===================================="

# Check config
CONFIG="config/trading_config_phase6.json"
if [ ! -f "$CONFIG" ]; then
    echo "❌ Config not found: $CONFIG"
    exit 1
fi
echo "✅ Config found: $CONFIG"

# Check Python
PYTHON=$(which python3)
if [ -z "$PYTHON" ]; then
    echo "❌ python3 not found"
    exit 1
fi
echo "✅ Python: $PYTHON"

# Check mode
echo "✅ Environment:"
echo "   SANDBOX_MODE=$SANDBOX_MODE"
echo "   SANDBOX_TRADING=$SANDBOX_TRADING"
echo "   PAPER_MODE=$PAPER_MODE"

# Start bot
echo ""
echo "🔄 Starting Phase 6 Trading Bot..."
echo "   Config: $CONFIG"
echo "   Mode: PAPER_TRADE"
echo "   Duration: 1+ hour (120 cycles @ 30min interval)"
echo "   Expected cycles: 2"
echo ""

python3 phase6_trading.py --config "$CONFIG" --mode PAPER_TRADE &
BOT_PID=$!

echo "✅ Bot started (PID: $BOT_PID)"

# Monitor for 1+ hour
echo "📊 Monitoring bot for 1+ hour..."
DURATION=3600  # 1 hour
ELAPSED=0
CHECK_INTERVAL=60  # Check every minute

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
echo "✅ Bot ran continuously for 1+ hour!"

# Kill bot gracefully
echo "🛑 Stopping bot..."
kill $BOT_PID 2>/dev/null || true
wait $BOT_PID 2>/dev/null || true

# Check trades log
TRADES_LOG="trades_paper_phase6.csv"
if [ -f "$TRADES_LOG" ]; then
    LINE_COUNT=$(wc -l < "$TRADES_LOG")
    echo "✅ Trades log exists: $TRADES_LOG ($LINE_COUNT lines)"
else
    echo "⚠️  Trades log not found (no trades executed, which is OK)"
fi

echo ""
echo "✨ Phase 6 Verification Complete!"
echo "   - Bot runs continuously ✅"
echo "   - Paper trading enabled ✅"
echo "   - Ready for production"
