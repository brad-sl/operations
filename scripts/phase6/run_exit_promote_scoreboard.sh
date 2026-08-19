#!/usr/bin/env bash
# GAP-01 exit promote scoreboard
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec .venv/bin/python phase6/research/run_exit_promote_scoreboard.py "$@"
