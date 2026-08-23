#!/usr/bin/env bash
# Tier-1 vol+velocity risk scalar shadow — no agent, no orders
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 scripts/phase6/run_vol_risk_scalar_shadow.py --quiet-ok
