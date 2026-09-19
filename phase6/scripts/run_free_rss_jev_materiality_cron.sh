#!/usr/bin/env bash
# Free/RSS Jev materiality shadow — local log only.
# Does NOT write live sentiment_cache.json or change floors.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot || exit 1
mkdir -p logs/free_rss_jev
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="logs/free_rss_jev/${TS}.log"
# Prefer venv
PY=python3
if [[ -x .venv/bin/python3 ]]; then PY=.venv/bin/python3; fi
# After free shadow densifies RSS; judge top headlines only
"$PY" scripts/phase6/run_free_rss_jev_materiality.py --max-judge 24 --max-calls-day 96 \
  >"$LOG" 2>&1 || true
tail -n 30 "$LOG" || true
exit 0
