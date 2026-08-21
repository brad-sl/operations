#!/usr/bin/env bash
# Bear ladder promote-watch wrapper (Hermes scripts dir — no path traversal).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
if [[ -x "$ROOT/.venv/bin/python3" ]]; then
  exec "$ROOT/.venv/bin/python3" "$ROOT/phase6/research/run_bear_ladder_promote_watch.py"
fi
exec python3 "$ROOT/phase6/research/run_bear_ladder_promote_watch.py"
