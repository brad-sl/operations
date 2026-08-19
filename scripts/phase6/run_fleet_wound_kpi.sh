#!/usr/bin/env bash
# GAP-02 fleet wound KPI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec .venv/bin/python -m phase6.core.fleet_wound_kpi "$@"
