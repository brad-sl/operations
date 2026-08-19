#!/bin/bash
# Wrapper to run Phase 6 backtests on this CPU (avoids X86_V2 NumPy crash)
# Prefer project .venv (has numpy); fall back to python3 on PATH.
export OPENBLAS_CORETYPE=GENERIC
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  exec "$ROOT/.venv/bin/python3" "$@"
fi
exec python3 "$@"
