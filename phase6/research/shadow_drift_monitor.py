"""
Compare live shadow period PnL vs backtest prediction; trigger rollback on breach.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, PHASE6_LIVE_STATE, TRADING_CONFIG_PHASE6
from phase6.research.shadow_overlay_store import load_state, rollback_overlay

DRIFT_RETURN_PP = 12.0
DRIFT_DD_PP = 8.0
MIN_HOURS = 24


def _load_equity_usd() -> float:
    cfg_cap = 1000.0
    if TRADING_CONFIG_PHASE6.exists():
        with open(TRADING_CONFIG_PHASE6) as f:
            cfg_cap = float(json.load(f).get("global_settings", {}).get("total_capital", 1000))
    if PHASE6_LIVE_STATE.exists():
        with open(PHASE6_LIVE_STATE) as f:
            st = json.load(f)
        te = st.get("total_equity_usd")
        if te is not None:
            return float(te)
        for b in st.get("balances", []):
            if b.get("currency") == "USD":
                return float(b.get("balance", 0))
    return cfg_cap


def _hours_since(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return 0.0


def evaluate_drift() -> Dict[str, Any]:
    state = load_state()
    if not state.get("active"):
        return {"status": "inactive"}

    baseline = float(state.get("baseline_equity_usd") or 0)
    current = _load_equity_usd()
    if baseline <= 0:
        baseline = current

    live_return_pct = (current / baseline - 1.0) * 100.0 if baseline > 0 else 0.0
    pred = state.get("predicted") or {}
    pred_return = float(pred.get("total_return_pct") or 0)
    pred_dd = float(pred.get("max_drawdown_pct") or 0)

    live_dd_pct = max(0.0, (baseline - current) / baseline * 100.0) if current < baseline else 0.0

    hours = _hours_since(state.get("activated_at", ""))
    breaches: List[str] = []

    if hours >= MIN_HOURS and live_return_pct < pred_return - DRIFT_RETURN_PP:
        breaches.append(
            f"return drift: live {live_return_pct:.2f}% vs predicted {pred_return:.2f}% (>{DRIFT_RETURN_PP}pp)"
        )
    if live_dd_pct > pred_dd + DRIFT_DD_PP:
        breaches.append(
            f"drawdown breach: live {live_dd_pct:.2f}% vs predicted max_dd {pred_dd:.2f}% (+{DRIFT_DD_PP}pp slack)"
        )

    report = {
        "status": "active",
        "proposal_id": state.get("proposal_id"),
        "scenario_id": state.get("scenario_id"),
        "source_run_id": state.get("source_run_id"),
        "hours_elapsed": round(hours, 1),
        "baseline_equity_usd": baseline,
        "current_equity_usd": round(current, 2),
        "live_return_pct": round(live_return_pct, 3),
        "predicted_return_pct": pred_return,
        "live_drawdown_pct": round(live_dd_pct, 3),
        "predicted_max_drawdown_pct": pred_dd,
        "breaches": breaches,
        "monitor_ok": len(breaches) == 0,
    }
    return report


def run_monitor_and_rollback() -> Dict[str, Any]:
    report = evaluate_drift()
    if report.get("status") != "active":
        return report

    out_path = PROJECT_ROOT / "data/state/analyst_shadow_drift_latest.json"
    with open(out_path, "w") as f:
        json.dump({**report, "checked_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)

    if report.get("breaches"):
        rb = rollback_overlay("; ".join(report["breaches"]), breach=True)
        report["rollback"] = rb
        _append_drift_learning(report)
    return report


def _append_drift_learning(report: Dict[str, Any]) -> None:
    path = PROJECT_ROOT / "data/state/analyst_learnings.json"
    data = {"learnings": []}
    if path.exists():
        with open(path) as f:
            data = json.load(f)
    data.setdefault("learnings", []).append(
        {
            "cycle": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "thesis": f"Shadow trial {report.get('proposal_id')} would match backtest run {report.get('source_run_id')}",
            "outcome": (
                f"Drift breach after {report.get('hours_elapsed')}h: "
                f"live return {report.get('live_return_pct')}% vs pred {report.get('predicted_return_pct')}%"
            ),
            "evolution_note": "Rollback overlay; tighten gates or fix SL/execution gaps before re-trial",
            "date": datetime.now(timezone.utc).isoformat(),
        }
    )
    data["learnings"] = data["learnings"][-25:]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)