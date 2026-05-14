#!/bin/bash
# Status verification script for Trading Monitor agent
# Use this to verify Phase 5.1 & Phase 6 status from correct paths

CRYPTO_BOT_ROOT="/home/brad/.openclaw/workspace/operations/crypto-bot"
cd "$CRYPTO_BOT_ROOT"

echo "=== TRADING MONITOR STATUS VERIFICATION ==="
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# Check processes
PHASE5_COUNT=$(ps aux | grep -c "[p]hase5_multi_pair")
echo "✅ Processes running: $PHASE5_COUNT (should be 2 if both phases active)"

# Check sentiment cache
if [ -f sentiment_cache.json ]; then
    SENTIMENT_AGE=$(find sentiment_cache.json -mmin -60 2>/dev/null | wc -l)
    if [ "$SENTIMENT_AGE" -gt 0 ]; then
        echo "✅ Sentiment cache: Fresh (< 60 min old)"
    else
        echo "⚠️  Sentiment cache: Stale (> 60 min old)"
    fi
else
    echo "❌ Sentiment cache: Missing"
fi

# Check CSV
if [ -f trades_sandbox.csv ]; then
    ROWS=$(wc -l < trades_sandbox.csv)
    echo "✅ Trades CSV: Exists ($ROWS rows)"
else
    echo "❌ Trades CSV: Missing"
fi

# Check logs
if [ -f logs/phase5_live.log ]; then
    echo "✅ Phase5 log: Exists"
else
    echo "❌ Phase5 log: Missing"
fi

if [ -f logs/phase6_paper.log ]; then
    echo "✅ Phase6 log: Exists"
else
    echo "❌ Phase6 log: Missing"
fi

echo ""
echo "Working directory: $CRYPTO_BOT_ROOT"
