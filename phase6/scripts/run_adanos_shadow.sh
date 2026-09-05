#!/usr/bin/env bash
# Adanos Reddit-crypto shadow (2×/day pre-X) + multi-way correlate vs RSS/free/X.
# SHADOW only — does NOT write live sentiment_cache.json / does NOT change gates.
# Free tier ~2 API calls/run · keep ≤2×/day (250 req/mo).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"
# Prefer project venv; fall back to PATH python3
if [[ -x "${ROOT}/.venv/bin/python3" ]]; then
  PY="${ROOT}/.venv/bin/python3"
else
  PY="$(command -v python3)"
fi
LOG="${ROOT}/logs/adanos_shadow.log"
mkdir -p "${ROOT}/logs"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  echo "=== ${TS} adanos shadow ==="
  # Key from project .env via load_project_dotenv inside fetcher
  set +e
  "$PY" fetch_adanos_sentiment.py
  RC_A=$?
  "$PY" phase6/scripts/correlate_adanos_rss_free_x.py
  RC_C=$?
  set -e
  echo "rc_adanos=${RC_A} rc_corr=${RC_C}"
} >>"$LOG" 2>&1

# stdout for hermes no_agent:
#  - empty on normal success (deliver=local, no spam)
#  - short FAIL line on missing key / hard error (failure_deliver=origin)
"$PY" - <<'PY'
import json
import sys
from pathlib import Path

cache = Path("data/state/adanos_sentiment_cache.json")
corr = Path("data/state/adanos_rss_free_x_correlation_latest.json")
if not cache.exists():
    print("ADANOS_SHADOW FAIL: no cache")
    sys.exit(0)
try:
    d = json.loads(cache.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ADANOS_SHADOW FAIL: bad cache ({e})")
    sys.exit(0)
st = d.get("status") or ""
if st == "missing_api_key":
    print("ADANOS_SHADOW FAIL: missing ADANOS_API_KEY")
    sys.exit(0)
if st == "error":
    errs = (d.get("meta") or {}).get("errors") or []
    print(f"ADANOS_SHADOW FAIL: status=error errs={errs[:2]}")
    sys.exit(0)
# success / partial → silent
# optional: latch note if first multi-day ready (not used yet)
if corr.exists():
    try:
        c = json.loads(corr.read_text(encoding="utf-8"))
        rank0 = (c.get("ranking_vs_x") or [{}])[0]
        # keep silent; log path only on promote-class later
        _ = rank0
    except Exception:
        pass
sys.exit(0)
PY
