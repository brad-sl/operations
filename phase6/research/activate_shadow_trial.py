#!/usr/bin/env python3
"""
Activate ANALYST-OPT shadow trial from a proposed backlog entry (gates must have passed at ingest).

Does NOT enable live trading — overlay merges in-memory in Phase6Runner only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.production_period_baseline import compute_since_go_live
from phase6.research.shadow_overlay_store import activate_overlay


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposal-id", required=True)
    ap.add_argument("--regime-adaptive", action="store_true", help="Enable regime knob map swaps")
    args = ap.parse_args()

    backlog_path = ROOT / "data/state/analyst_proposed_backlog.json"
    with open(backlog_path) as f:
        backlog = json.load(f)
    proposal = next(
        (p for p in backlog.get("proposals", []) if p.get("id") == args.proposal_id),
        None,
    )
    if not proposal:
        print(f"proposal not found: {args.proposal_id}")
        return 1

    lb_path = ROOT / "data/state/analyst_scenario_leaderboard_latest.json"
    with open(lb_path) as f:
        lb = json.load(f)
    scenario_id = proposal.get("scenario_id")

    pack_path = ROOT / "phase6/research/scenarios" / f"{lb.get('pack_id')}.json"
    pack = None
    if pack_path.exists():
        with open(pack_path) as f:
            pack = json.load(f)
    else:
        pack = {"default_engine": lb.get("engine_mode", "arch4"), "scenarios": []}

    pack_scenarios = pack.get("scenarios") or []
    scenario = next((s for s in pack_scenarios if s["id"] == scenario_id), None)
    if not scenario:
        scenario = {"id": scenario_id, "backtest": {}, "arch4": {}}

    sc_row = next((s for s in lb.get("scenarios", []) if s["id"] == scenario_id), {})
    metrics = sc_row.get("metrics") or {}
    prod = compute_since_go_live()
    equity = float(prod.get("end_equity_usd") or prod.get("initial_capital_usd") or 1000)

    state = activate_overlay(
        proposal,
        scenario,
        pack,
        predicted_metrics={
            "total_return_pct": metrics.get("total_return_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
        },
        baseline_equity_usd=equity,
        enable_regime_policy=args.regime_adaptive,
    )
    print(f"Shadow overlay ACTIVE proposal={state['proposal_id']} scenario={state['scenario_id']}")
    print(f"  snapshot: {state.get('config_snapshot_path')}")
    print(f"  regime_policy: {state.get('regime_policy', {}).get('enabled')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())