#!/usr/bin/env bash
# pre_ship_quality.sh — run before runner bounce or money-path commit.
# Exit 0 pass, 2 P0 fail.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PY="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
exec "$PY" "${PROJECT_ROOT}/scripts/hermes/pre_ship_quality.py" "$@"
