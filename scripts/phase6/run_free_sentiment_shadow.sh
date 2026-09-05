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
# stdout for hermes no_agent: silent on normal ticks (deliver=local).
# Only print when promote_ready flips true or correlate missing — avoid 2h spam.
"$PY" - <<'PY'
import json
from pathlib import Path
p = Path("data/state/free_vs_x_correlation_latest.json")
flag = Path("data/state/free_sentiment_promote_ready_latched.json")
if not p.exists():
    print("FREE_SHADOW: no correlation yet")
else:
    d = json.loads(p.read_text())
    ready = bool(d.get("promote_ready"))
    prev = False
    if flag.exists():
        try:
            prev = bool(json.loads(flag.read_text()).get("promote_ready"))
        except Exception:
            prev = False
    flag.write_text(json.dumps({"promote_ready": ready, "ts": d.get("timestamp")}, indent=2))
    if ready and not prev:
        print(
            f"FREE_SHADOW promote_ready=TRUE "
            f"free_nz={d.get('n_free_nz')} overlap={d.get('n_overlap')} "
            f"sign={d.get('sign_agreement')} spearman={d.get('spearman_all')}"
        )
    # else: empty stdout = silent
PY
