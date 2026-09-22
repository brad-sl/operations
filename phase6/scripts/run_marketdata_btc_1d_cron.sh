#!/usr/bin/env bash
# Quiet BTC 1d marketdata ingest + regime board (D2). Measure/sensor only — no knobs.
set -euo pipefail
ROOT="${PROJECT_ROOT:-/home/brad/projects/crypto-trading-bot}"
cd "$ROOT"
export PYTHONPATH=.
LOG_DIR="$ROOT/logs/marketdata"
mkdir -p "$LOG_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/${STAMP}.log"
PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then PY=python3; fi

{
  echo "=== marketdata btc 1d $STAMP ==="
  "$PY" scripts/phase6/run_marketdata_btc_1d.py all --mirror-json
  # Refresh REGIME-CASH status SSOT from honest detector (policy map only — no knob GO)
  "$PY" - <<'PY'
from phase6.core.regime_cash_policy import load_policy, persist_status, resolve_regime_cash
snap = resolve_regime_cash(policy=load_policy())
path = persist_status(snap)
print(f"regime_cash_status refreshed → {snap.regime} btc30d={snap.btc_return_pct} path={path}")
PY
} 2>&1 | tee "$LOG"

# Short stdout for Telegram when deliver=telegram
"$PY" - <<'PY'
import sys
sys.path.insert(0, ".")
from phase6.core.marketdata_store import db_stats
from phase6.research.regime_detector import detect_regime
st = db_stats()
d = detect_regime(use_live_price=True)
fr = (st.get("freshness") or [{}])
btc = next((x for x in fr if x.get("symbol")=="BTC-USD" and x.get("granularity_sec")==86400), {})
print(
  f"MD·BTC1d bars={st.get('bars')} status={btc.get('status')} "
  f"gap={btc.get('gap_days_tail')} · REGIME {d.get('regime')}/{d.get('regime_layer')} "
  f"30d={d.get('btc_return_pct')} src={d.get('data_source')} fresh={d.get('fresh_ok')}"
)
PY
