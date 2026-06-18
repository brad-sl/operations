#!/bin/bash
# 30min sentiment cron wrapper (no-agent)
export OPENBLAS_CORETYPE=GENERIC
cd "$(dirname "$0")"
python3 run_sentiment_system.py
