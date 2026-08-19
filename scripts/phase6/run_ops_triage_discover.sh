#!/usr/bin/env bash
# Phase1 cost: deterministic morning ops triage (no LLM).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"
exec .venv/bin/python3 scripts/phase6/ops_triage_discover.py
