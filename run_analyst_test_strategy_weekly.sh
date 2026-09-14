#!/usr/bin/env bash
# Hermes no_agent: analyst-test-strategy-weekly
# Weekly: status + sync-active + emit (capacity-gated).
# Telegram (stdout) = short board only. Full JSON → logs/ (Brad GO 2026-09-14 option A).
# No live trading config writes.
set -euo pipefail

ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

mkdir -p logs
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="logs/analyst_test_strategy_weekly"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/${STAMP}.log"
LATEST_LOG="${LOG_DIR}/latest.log"
STATUS_JSON="${LOG_DIR}/status_latest.json"
SYNC_JSON="${LOG_DIR}/sync_latest.json"
EMIT_JSON="${LOG_DIR}/emit_latest.json"

{
  echo "# analyst-test-strategy-weekly full dump"
  echo "Run: $(date -Iseconds)"
  echo
  echo "## Status"
  "$PY" phase6/research/analyst_test_strategy.py status | tee "$STATUS_JSON"
  echo
  echo "## Sync active"
  "$PY" phase6/research/analyst_test_strategy.py sync-active | tee "$SYNC_JSON"
  echo
  echo "## Emit (gated by capacity; ≤1 if free)"
  "$PY" phase6/research/analyst_test_strategy.py emit | tee "$EMIT_JSON" || true
  echo
} >"$LOG" 2>&1
cp -f "$LOG" "$LATEST_LOG"

# stdout = Telegram body only (short board). Empty emit still gets a compact weekly line.
"$PY" - <<'PYEOF'
import json
from pathlib import Path
from datetime import datetime, timezone

log_dir = Path("logs/analyst_test_strategy_weekly")
s_path = Path("data/state/trials/TEST_STRATEGY.json")
s = json.loads(s_path.read_text()) if s_path.exists() else {}
slots = s.get("slots") or {}
cap = s.get("capacity") or {}
roadmap = s.get("roadmap") or []
planned = [p.get("plan_id") for p in roadmap if p.get("status") == "planned"]
running = [
    f"{p.get('plan_id')}:{p.get('master_id') or '-'}"
    for p in roadmap
    if p.get("status") == "running"
]
emitted = []
emit_path = log_dir / "emit_latest.json"
if emit_path.exists():
    try:
        raw = emit_path.read_text().strip()
        # tee may include only JSON object
        ej = json.loads(raw) if raw.startswith("{") else {}
        emitted = ej.get("emitted") or []
    except Exception:
        emitted = []

off = slots.get("offline_running", 0)
ins = slots.get("instru_running", 0)
rev = slots.get("review_pending", 0)
max_off = cap.get("max_offline_analysis", 1)
max_ins = cap.get("max_parallel_instrumentation", 1)
max_rev = cap.get("max_review_pending", 2)
active = s.get("active_master_ids") or []
regime = s.get("live_regime") or "—"

lines = [
    "analyst-test-strategy-weekly",
    f"Slots: offline={off}/{max_off} · instru={ins}/{max_ins} · review={rev}/{max_rev}",
    f"Regime: {regime}",
    f"Active: {active or '—'}",
]
if running:
    lines.append(f"Running: {running[:3]}")
if planned:
    lines.append(f"Planned next: {planned[:3]}")
if emitted:
    ids = [e.get("master_id") or e.get("plan_id") for e in emitted]
    lines.append(f"Emitted: {ids}")
else:
    lines.append("Emitted: none (capacity or no planned unlock)")
lines.append("No live config writes.")
lines.append(f"Full log: {log_dir / 'latest.log'}")
print("\n".join(lines))
PYEOF
