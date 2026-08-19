#!/usr/bin/env python3
"""
RC-06: Continuous REGIME-CASH loop — detect → status → knob map → param sweep → analysis.

Never auto-promotes live config. Writes:
  data/state/regime_cash_status.json
  data/state/regime_cash_param_sweep_latest.json
  data/state/regime_cash_optimization_latest.json
  data/state/regime_cash_learnings.jsonl (append)

Intended for cron (weekly after OPT or daily light).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import load_policy, persist_status, resolve_regime_cash

OUT = ROOT / "data/state/regime_cash_optimization_latest.json"
LEARN = ROOT / "data/state/regime_cash_learnings.jsonl"
SCORECARD = ROOT / "data/state/analyst_regime_scorecard_latest.json"
KNOB_APPLY = ROOT / "phase6/research/apply_regime_knob_map_from_scorecard.py"
SWEEP = ROOT / "phase6/research/run_regime_cash_param_sweep.py"


def _run(script: Path) -> Dict[str, Any]:
    if not script.exists():
        return {"ok": False, "error": f"missing {script}"}
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
        timeout=600,
    )
    return {
        "ok": r.returncode == 0,
        "returncode": r.returncode,
        "stdout": (r.stdout or "")[-2000:],
        "stderr": (r.stderr or "")[-1000:],
    }


def main() -> int:
    ts = datetime.now(timezone.utc).isoformat()
    steps: Dict[str, Any] = {}

    # 1) Active regime + cash policy snapshot
    pol = load_policy()
    snap = resolve_regime_cash(policy=pol)
    status_path = persist_status(snap)
    steps["resolve"] = {
        "regime": snap.regime,
        "strategy_mode": snap.strategy_mode,
        "allow_new_buys": snap.allow_new_buys,
        "btc_return_pct": snap.btc_return_pct,
        "status_path": str(status_path),
    }

    # 2) Refresh knob map from scorecard if present
    if SCORECARD.exists():
        steps["knob_map"] = _run(KNOB_APPLY)
    else:
        steps["knob_map"] = {"ok": False, "error": "no scorecard"}

    # 3) Param sweep
    steps["param_sweep"] = _run(SWEEP)

    sweep_path = ROOT / "data/state/regime_cash_param_sweep_latest.json"
    sweep = {}
    if sweep_path.exists():
        sweep = json.loads(sweep_path.read_text(encoding="utf-8"))

    # 4) Analysis attributes for optimization
    attributes = {
        "active_regime": snap.regime,
        "park": snap.strategy_mode == "usdc_park" or not snap.allow_new_buys,
        "entry_min_sentiment": (snap.entry or {}).get("min_sentiment"),
        "entry_max_rsi": (snap.entry or {}).get("max_rsi"),
        "target_max_util_pct": snap.target_max_util_pct,
        "rebalance_cap_usd": snap.rebalance_cap_usd,
        "detector": snap.detector,
        "sweep_best": (sweep.get("best") or {}),
        "sweep_improves": (sweep.get("suggestions") or {}).get("improves_score"),
        "objective": (pol.get("optimization") or {}).get("objective"),
    }

    # Profit-max / downside-min guidance (human + gated OPT only)
    recommendations = []
    if snap.strategy_mode == "usdc_park":
        recommendations.append(
            {
                "action": "keep_park",
                "detail": f"Regime {snap.regime}: block new BUYs; prefer USDC/cash; SELLs allowed",
                "priority": "P0",
            }
        )
    else:
        recommendations.append(
            {
                "action": "deploy_gated",
                "detail": f"Regime {snap.regime}: allow buys only if RSI≤{snap.entry.get('max_rsi')} and sentiment≥{snap.entry.get('min_sentiment')}",
                "priority": "P1",
            }
        )
    if (sweep.get("suggestions") or {}).get("improves_score"):
        recommendations.append(
            {
                "action": "review_detector_thresholds",
                "detail": "Param sweep found better score than current detector knobs — review candidate_detector, do not auto-apply",
                "candidate": (sweep.get("suggestions") or {}).get("candidate_detector"),
                "priority": "P2",
            }
        )
    recommendations.append(
        {
            "action": "continue_scorecard_opt",
            "detail": "Weekly OPT + regime scorecard remain source of strategy_mode winners; cash policy enforces entry",
            "priority": "P1",
        }
    )

    payload = {
        "generated_at": ts,
        "schema": "regime_cash_optimization_v1",
        "auto_promote": False,
        "steps": steps,
        "attributes": attributes,
        "recommendations": recommendations,
        "gates": {
            "live_param_audit_required": True,
            "usdc_hurdle_required": True,
            "shadow_before_live": True,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    learn_row = {
        "ts": ts,
        "regime": snap.regime,
        "strategy_mode": snap.strategy_mode,
        "btc_return_pct": snap.btc_return_pct,
        "allow_new_buys": snap.allow_new_buys,
        "sweep_best_score": (sweep.get("best") or {}).get("score"),
        "recommendations": [r.get("action") for r in recommendations],
    }
    with LEARN.open("a", encoding="utf-8") as f:
        f.write(json.dumps(learn_row) + "\n")

    print(f"REGIME-CASH continuous OK regime={snap.regime} mode={snap.strategy_mode} → {OUT}")
    for r in recommendations:
        print(f"  [{r['priority']}] {r['action']}: {r['detail'][:100]}")
    return 0 if steps.get("param_sweep", {}).get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
