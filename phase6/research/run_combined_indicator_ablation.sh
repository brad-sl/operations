#!/usr/bin/env bash
# Thin wrapper: multi-pair combined indicator ablation dig pass.
set -euo pipefail
cd /home/brad/projects/crypto-trading-bot
export OPENBLAS_CORETYPE=GENERIC
exec .venv/bin/python3 phase6/research/combined_strategy_backtest.py \
  --pairs btc,eth,sol,link,avax
