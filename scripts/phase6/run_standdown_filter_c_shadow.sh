#!/usr/bin/env bash
# Stand-down filter C shadow — no orders, no config.
# Quiet-ok: empty stdout when nothing would-block (local deliver = silent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
exec .venv/bin/python scripts/phase6/run_standdown_filter_c_shadow.py --quiet-ok "$@"
