#!/usr/bin/env bash
# Ops Issue Loop tick — sync GH → route → Kanban ensure → reconcile.
# Hermes no_agent cron wrapper (copy to ~/.hermes/scripts/phase6/).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"
exec .venv/bin/python3 scripts/phase6/ops_issue_loop.py run --gh-assign --dispatch
