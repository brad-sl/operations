#!/bin/bash
# Official wrapper for the SINGLE canonical sentiment collector (v3)
# Uses Apify actor with native sentiment for maximum simplicity and reliability.
# Writes exclusively to sentiment_cache.json (project root).
# All trading scripts, reports, and dashboards read from this via phase6/core/sentiment_scorer.py
#
# Timeout allows 5 minutes for Apify crawl + processing.

cd "$(dirname "$0")/.."
source .env 2>/dev/null || true

echo "[$(date)] Starting CANONICAL sentiment collection (v3 actor-native)..."
timeout 300 python3 run_full_sentiment_v3.py
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 124 ]; then
    echo "[$(date)] Canonical sentiment collection completed (or timed out gracefully)."
else
    echo "[$(date)] Canonical sentiment collection exited with code $EXIT_CODE"
fi
