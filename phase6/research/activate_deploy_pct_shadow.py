#!/usr/bin/env python3
"""
Activate in-memory ANALYST shadow overlay: bump deploy_pct only (lean-in, live-safe).

Does not write trading_config_phase6.json. Replaces any active overlay after optional rollback.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.production_period_baseline import compute_since_go_live
from phase6.research.shadow_overlay_store import (
    OVERLAY_DIR,
    _snapshot_to_git,
    load_state,
    rollback_overlay,
    save_state,
)

PROPOSAL_ID = "DEPLOY-PCT-078-LEAN-IN"
BASE_DEPLOY = 0.72
SHADOW_DEPLOY = 0.78


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy-pct", type=float, default=SHADOW_DEPLOY)
    ap.add_argument("--replace", action="store_true", help="Rollback active overlay first")
    args = ap.parse_args()

    state = load_state()
    if state.get("active"):
        if not args.replace:
            print(
                f"Overlay already active ({state.get('proposal_id')}). "
                "Pass --replace to swap to deploy_pct shadow."
            )
            return 1
        rb = rollback_overlay(f"replaced by {PROPOSAL_ID}")
        print("rolled back:", rb)

    prod = compute_since_go_live()
    equity = float(prod.get("end_equity_usd") or prod.get("initial_capital_usd") or 0)
    if equity <= 0:
        from phase6.research.shadow_drift_monitor import _load_equity_usd

        equity = _load_equity_usd()

    payload = {
        "active": True,
        "mode": "shadow",
        "proposal_id": PROPOSAL_ID,
        "source_run_id": "ANALYST-OPT-LEAN-IN-WR-GUARD-20260712",
        "scenario_id": "deploy_pct_lean_in",
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_equity_usd": round(equity, 2),
        "predicted": {
            "note": "Path B has no deploy_pct knob; monitor uses live equity vs baseline at activation",
            "deploy_pct_baseline": BASE_DEPLOY,
            "deploy_pct_shadow": args.deploy_pct,
            "scale_factor": round(args.deploy_pct / BASE_DEPLOY, 4),
            "total_return_pct": None,
            "max_drawdown_pct": None,
        },
        "knobs": {
            "use_rotation": True,
            "rebal_freq": 7,
            "deploy_pct_shadow": args.deploy_pct,
        },
        "live_overlay": {
            "risk_management.deploy_pct": float(args.deploy_pct),
            "global_settings.rebalance_cap_usd": 200.0,
        },
        "gap_flags": [
            "DEPLOY_PCT_NOT_IN_ARCH4_HARNESS",
            "SHADOW_IN_MEMORY_ONLY",
            "REBALANCE_CAP_PROXY_FOR_BACKTEST",
        ],
        "regime_policy": {"enabled": False},
    }
    snap = _snapshot_to_git(PROPOSAL_ID, payload)
    payload["config_snapshot_path"] = snap

    base_cfg = ROOT / "config/trading_config_phase6.json"
    if base_cfg.exists():
        import shutil

        OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_cfg, OVERLAY_DIR / f"{PROPOSAL_ID}_base_config.json")

    hist = (load_state().get("history") or [])[-20:]
    save_state({**payload, "history": hist})

    print(f"Shadow ACTIVE proposal={PROPOSAL_ID} deploy_pct={args.deploy_pct} (was {BASE_DEPLOY})")
    print(f"  baseline_equity_usd={payload['baseline_equity_usd']}")
    print(f"  snapshot: {snap}")
    print("  Restart runner to pick up overlay: bash scripts/phase6/start_phase6_runner.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())