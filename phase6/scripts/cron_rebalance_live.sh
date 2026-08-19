#!/usr/bin/env bash
# Hermes no_agent: Phase6 live rebalance trigger (morning/evening/midday).
# When continuous runner is up, touches force_rebalance.flag (no duplicate process).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi
exec "$PY" phase6/scripts/cron_rebalance.py --live
