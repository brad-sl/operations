#!/usr/bin/env bash
# Boundary-layer cream shadow — no live orders. Appends jsonl + latest report.
set -euo pipefail
# Resolve through symlink so Hermes ~/.hermes/scripts/ link works
SRC="${BASH_SOURCE[0]}"
while [[ -L "$SRC" ]]; do
  DIR="$(cd -P "$(dirname "$SRC")" && pwd)"
  SRC="$(readlink "$SRC")"
  [[ "$SRC" != /* ]] && SRC="$DIR/$SRC"
done
ROOT="$(cd -P "$(dirname "$SRC")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi
exec "$PY" phase6/research/run_regime_boundary_layer_shadow.py
