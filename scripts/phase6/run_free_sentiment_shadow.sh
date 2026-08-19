#!/usr/bin/env bash
# Phase2: free sentiment shadow refresh + correlate vs X (no live cutover).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"
PY="${ROOT}/.venv/bin/python3"
LOG="${ROOT}/logs/sentiment_free_shadow.log"
mkdir -p "${ROOT}/logs"
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) free shadow ==="
  "$PY" phase6/scripts/refresh_sentiment_free.py
  "$PY" phase6/scripts/correlate_free_vs_x_sentiment.py
} >>"$LOG" 2>&1
# stdout for hermes no_agent delivery: one-line summary
"$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/state/free_vs_x_correlation_latest.json")
if not p.exists():
    print("FREE_SHADOW: no correlation yet")
else:
    d = json.loads(p.read_text())
    print(
        f"FREE_SHADOW promote_ready={d.get('promote_ready')} "
        f"free_nz={d.get('n_free_nz')} overlap={d.get('n_overlap')} "
        f"sign={d.get('sign_agreement')} spearman={d.get('spearman_all')}"
    )
PY
