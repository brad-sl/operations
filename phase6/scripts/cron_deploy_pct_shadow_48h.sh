#!/usr/bin/env bash
# One-shot: surface DEPLOY-PCT-078-LEAN-IN shadow eval after ~48h (cron no_agent).
set -euo pipefail
ROOT="/home/brad/projects/crypto-trading-bot"
cd "$ROOT"
export OPENBLAS_CORETYPE=GENERIC
export PYTHONPATH=.

EVAL_JSON="$ROOT/data/state/deploy_pct_shadow_eval_latest.json"
OVERLAY="$ROOT/data/state/analyst_shadow_overlay.json"

/usr/bin/python3 phase6/research/run_deploy_pct_shadow_eval.py >/tmp/deploy_pct_shadow_eval_run.log 2>&1 || true

python3 <<'PY'
import json
from pathlib import Path
from datetime import datetime, timezone

root = Path("/home/brad/projects/crypto-trading-bot")
eval_path = root / "data/state/deploy_pct_shadow_eval_latest.json"
overlay_path = root / "data/state/analyst_shadow_overlay.json"

def load(p):
    if not p.exists():
        return {}
    return json.loads(p.read_text())

ev = load(eval_path)
ov = load(overlay_path)
dr = ev.get("shadow_drift") or {}
ew = ev.get("exit_wr") or {}
ret = ev.get("retrospective_rebalance") or {}
prod = ev.get("live_production_since_go_live") or {}

lines = [
    "**Deploy_pct shadow — 48h check**",
    f"Proposal: `{ov.get('proposal_id', 'n/a')}` | active: `{ov.get('active')}`",
    f"deploy_pct: **0.78** (baseline 0.72)",
    "",
    "**Drift monitor**",
    f"- hours: {dr.get('hours_elapsed', 'n/a')}",
    f"- baseline equity: ${dr.get('baseline_equity_usd', 'n/a')}",
    f"- current equity: ${dr.get('current_equity_usd', 'n/a')}",
    f"- live return since activation: {dr.get('live_return_pct', 'n/a')}%",
    f"- monitor_ok: {dr.get('monitor_ok', 'n/a')}",
]
if dr.get("breaches"):
    lines.append(f"- breaches: {dr['breaches']}")

lines += [
    "",
    "**Exit WR** (dash window)",
    f"- {ew.get('wins', '?')}/{ew.get('total', '?')} = {round((ew.get('win_ratio') or 0)*100, 1)}%",
    "",
    "**Rebalance deploy proxy (historical log)**",
    f"- shadow scale +{round((ret.get('scale_factor') or 1)-1, 4)*100:.1f}% → +${ret.get('delta_deploy_usd', 'n/a')} notional in log",
    "",
    f"Full JSON: `data/state/deploy_pct_shadow_eval_latest.json`",
    f"Checked: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
]
print("\n".join(lines))
PY