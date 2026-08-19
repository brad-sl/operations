#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec .venv/bin/python -m phase6.research.run_liquidation_redeploy_study "$@"
