#!/usr/bin/env bash
# Fee tier drift watch — refresh snapshot, TG body only on ≥5 bps drift (else empty).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
mkdir -p logs
# stderr → log; stdout clean for Hermes telegram deliver
exec .venv/bin/python scripts/phase6/run_fee_tier_drift_watch.py "$@" 2>>logs/fee_tier_drift_watch.log
