#!/usr/bin/env bash
# Limit-first buy shadow Phase C — no orders, no config.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
exec .venv/bin/python scripts/phase6/run_limit_first_buy_shadow.py --quiet-ok "$@"
