#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
exec .venv/bin/python scripts/phase6/run_limit_first_buy_pilot.py --quiet-ok "$@"
