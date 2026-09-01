#!/usr/bin/env bash
# Fee tier snapshot — read-only, no orders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
exec .venv/bin/python scripts/phase6/run_fee_tier_snapshot.py --quiet-ok "$@"
