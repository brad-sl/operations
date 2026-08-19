#!/usr/bin/env python3
"""
Evaluate deploy_pct shadow: retrospective rebalance scaling + ARCH-4 cap proxy (90d).

Real data only — no fabricated PnL.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.trade_ledger import TradeLedger
from phase6.research.production_period_baseline import compute_since_go_live
from phase6.research.shadow_drift_monitor import evaluate_drift
from phase6.research.shadow_overlay_store import load_state

REBAL_PATH = ROOT / "data/state/rebalance_history/default.jsonl"
OUT_PATH = ROOT / "data/state/deploy_pct_shadow_eval_latest.json"
BASE = 0.72


def _load_rebalances() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not REBAL_PATH.exists():
        return rows
    with open(REBAL_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def retrospective_scale(deploy_shadow: float) -> Dict[str, Any]:
    factor = deploy_shadow / BASE
    rows = _load_rebalances()
    live_rows = [
        r
        for r in rows
        if r.get("mode") == "live"
        and "capital_deployed_usd" in r
        and r.get("reason") == "daily_rebalance"
    ]
    if not live_rows:
        return {"status": "no_live_rebalance_rows", "factor": factor}

    base_deploy = sum(float(r.get("capital_deployed_usd") or 0) for r in live_rows)
    shadow_deploy = base_deploy * factor
    base_exec = sum(int(r.get("executed") or 0) for r in live_rows)
    return {
        "live_rebalance_events": len(live_rows),
        "sum_capital_deployed_usd_baseline": round(base_deploy, 2),
        "sum_capital_deployed_usd_shadow_scaled": round(shadow_deploy, 2),
        "delta_deploy_usd": round(shadow_deploy - base_deploy, 2),
        "scale_factor": round(factor, 4),
        "total_executed_trades_in_rebalance_log": base_exec,
        "interpretation": (
            "Hypothetical +8.3% notional on recorded rebalance deploy budgets "
            "(proxy until harness supports deploy_pct)."
        ),
    }


def arch4_cap_proxy() -> Dict[str, Any]:
    """Scale rebalance_cap by deploy ratio as ARCH-4 min_move proxy."""
    from datetime import date

    from phase6.research.arch4_scenario_runner import run_arch4_scenario
    from phase6.research.scenario_knobs import ScenarioKnobs

    start_d = date(2026, 4, 12)
    end_d = date(2026, 7, 11)
    base_cap = 200.0
    shadow_cap = round(base_cap * (SHADOW_DEPLOY / BASE), 2)

    def _knobs(sid: str, cap: float) -> ScenarioKnobs:
        return ScenarioKnobs(
            scenario_id=sid,
            rebalance_cap_usd=cap,
            rebalance_frequency_days=7,
            allocator_strategy="rotation",
            engine="arch4",
        )

    b = run_arch4_scenario(_knobs("deploy_proxy_base", base_cap), start_d, end_d)
    s = run_arch4_scenario(_knobs("deploy_proxy_shadow", shadow_cap), start_d, end_d)
    bm = b.get("metrics") or {}
    sm = s.get("metrics") or {}
    return {
        "window": {"start": start_d.isoformat(), "end": end_d.isoformat()},
        "baseline_cap_usd": base_cap,
        "shadow_cap_proxy_usd": shadow_cap,
        "baseline_metrics": {
            "return_pct": bm.get("total_return_pct"),
            "max_dd_pct": bm.get("max_drawdown_pct"),
            "sharpe": bm.get("sharpe_ratio"),
            "trades": bm.get("total_trades"),
            "avg_exposure_pct": bm.get("avg_exposure_pct"),
        },
        "shadow_metrics": {
            "return_pct": sm.get("total_return_pct"),
            "max_dd_pct": sm.get("max_drawdown_pct"),
            "sharpe": sm.get("sharpe_ratio"),
            "trades": sm.get("total_trades"),
            "avg_exposure_pct": sm.get("avg_exposure_pct"),
        },
        "caveat": "ARCH-4 Path B still lacks deploy_pct; cap/min_move proxy only.",
    }


SHADOW_DEPLOY = 0.78


def exit_wr_snapshot() -> Dict[str, Any]:
    led = TradeLedger()
    t = led.get_recent_trades(100)
    c = [x for x in t if x.get("pnl") is not None and float(x.get("pnl") or 0) != 0]
    w = sum(1 for x in c if float(x.get("pnl") or 0) > 0)
    return {
        "window": "last_100_ledger_rows_nonzero_pnl",
        "wins": w,
        "total": len(c),
        "win_ratio": round(w / len(c), 4) if c else None,
    }


def main() -> int:
    overlay = load_state()
    deploy_shadow = float(
        (overlay.get("live_overlay") or {}).get("risk_management.deploy_pct")
        or (overlay.get("predicted") or {}).get("deploy_pct_shadow")
        or SHADOW_DEPLOY
    )

    prod = compute_since_go_live()
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "overlay_active": bool(overlay.get("active")),
        "proposal_id": overlay.get("proposal_id"),
        "deploy_pct_baseline": BASE,
        "deploy_pct_shadow": deploy_shadow,
        "live_production_since_go_live": {
            "return_pct": prod.get("total_return_pct"),
            "end_equity_usd": prod.get("end_equity_usd"),
            "trade_count": prod.get("trade_count"),
        },
        "exit_wr": exit_wr_snapshot(),
        "retrospective_rebalance": retrospective_scale(deploy_shadow),
        "shadow_drift": evaluate_drift(),
    }

    try:
        report["arch4_cap_proxy_90d"] = arch4_cap_proxy()
    except Exception as e:
        report["arch4_cap_proxy_90d"] = {"error": str(e)}

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())