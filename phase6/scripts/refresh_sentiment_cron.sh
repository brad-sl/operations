#!/bin/bash
# Thin launcher for Hermes no_agent cron (Phase6 Sentiment/RSI Refresh)
# Enforces canonical project root per DATA_FLOW_AND_LOCATIONS.md
cd /home/brad/projects/crypto-trading-bot
exec python3 phase6/scripts/refresh_sentiment.py
