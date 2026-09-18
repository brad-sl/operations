#!/usr/bin/env bash
# One-call Brad-GO basket membership swap.
# Default dry-run dual_agree; --go applies. No orders / no live_swaps flip.
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
# shellcheck disable=SC1091
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
export PYTHONPATH=. PYTHONUNBUFFERED=1
export OPENBLAS_CORETYPE="${OPENBLAS_CORETYPE:-GENERIC}"
exec python3 scripts/phase6/basket_swap.py "$@"
