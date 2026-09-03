#!/usr/bin/env bash
# Hermes no_agent: analyst-test-strategy-weekly
# Weekly: status, sync-active, emit (if capacity), short board summary to stdout (for telegram delivery).
# Replaces LLM-driven cron (was prone to transient model provider reachability errors).
set -euo pipefail

ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT" || exit 1
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "# analyst-test-strategy-weekly"
echo "Run: $(date -Iseconds)"
echo

echo "## Status"
"$PY" phase6/research/analyst_test_strategy.py status
echo

echo "## Sync active"
"$PY" phase6/research/analyst_test_strategy.py sync-active
echo

echo "## Emit (gated by capacity; ≤1 if free)"
"$PY" phase6/research/analyst_test_strategy.py emit || true
echo

echo "## Short board summary"
"$PY" - << 'PYEOF'
import json, sys
from pathlib import Path
s = json.loads((Path("data/state/trials/TEST_STRATEGY.json")).read_text()) if Path("data/state/trials/TEST_STRATEGY.json").exists() else {}
slots = s.get("slots", {})
cap = s.get("capacity", {})
by = s.get("by_status", {})
planned = [p.get("plan_id") for p in s.get("roadmap", []) if p.get("status")=="planned"]
running = by.get("running", [])
print(f"Slots: offline={slots.get('offline_running')}/{cap.get('max_offline_analysis')}, instru={slots.get('instru_running')}/{cap.get('max_parallel_instrumentation')}, review_pending={slots.get('review_pending')}/{cap.get('max_review_pending')}")
print(f"Live regime: {s.get('live_regime')}")
print(f"Active: {s.get('active_master_ids', [])}")
print(f"Planned: {planned[:3]}")
print(f"Running: {running}")
print("No live config writes. (deterministic script)")
if not planned and slots.get('review_pending', 0) < cap.get('max_review_pending', 2):
    print("Capacity free; next weekly may emit if new roadmap planned items qualify.")
PYEOF

echo
echo "[SILENT] if nothing actionable."
