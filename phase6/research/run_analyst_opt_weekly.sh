#!/usr/bin/env bash
# Hermes no_agent cron: ANALYST-OPT weekly
set -euo pipefail
cd "$(dirname "$0")/../.."
exec .venv/bin/python3 phase6/research/run_analyst_opt_weekly.py