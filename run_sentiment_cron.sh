#!/bin/bash
# Hourly sentiment cache refresh for Phase 5 (X API v2 all pairs)
cd /home/brad/.openclaw/workspace/operations/crypto-bot
source venv/bin/activate
python3 fetch_x_sentiment.py >> logs/sentiment_fetch.log 2>&1
