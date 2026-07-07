"""
Format ANALYST-OPT leaderboard + production comparison for daily brief.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LATEST = ROOT / "data/state/analyst_scenario_leaderboard_latest.json"


def load_leaderboard(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    p = path or DEFAULT_LATEST
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def format_optimization_section(lb: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Returns (console text, brief JSON fragment)."""
    lines: List[str] = []
    lines.append("=== Optimization results (scenario vs production) ===")

    prod = lb.get("production") or {}
    since = lb.get("production_since_go_live") or {}
    overlap = prod.get("overlap_window")
    cov = prod.get("coverage", "none")

    if since.get("metrics"):
        sm = since["metrics"]
        lines.append(
            f"Production since go-live: return_pct={sm.get('total_return_pct')} "
            f"end_equity=${sm.get('end_equity_usd')} trades={sm.get('trade_count')} "
            f"live_rebalances={sm.get('live_rebalances_executed')}"
        )
        for n in since.get("notes") or []:
            lines.append(f"  note: {n}")

    if cov == "none":
        lines.append("Pack window has NO overlap with production trades — scenario sim uses OHLCV pack dates only.")
        for n in prod.get("notes") or []:
            lines.append(f"  {n}")
    else:
        pm = prod.get("metrics") or {}
        lines.append(
            f"Overlap {overlap}: production {lb.get('primary_metric')}={pm.get(lb.get('primary_metric'))} "
            f"return_pct={pm.get('total_return_pct')} realized_pnl=${pm.get('realized_pnl_usd')}"
        )

    winner = (lb.get("scenarios") or [{}])[0] if lb.get("ranking") else {}
    if lb.get("ranking"):
        winner_id = lb["ranking"][0]
        winner = next((s for s in lb.get("scenarios", []) if s["id"] == winner_id), winner)
    wm = winner.get("metrics") or {}
    lines.append(
        f"Scenario winner ({lb.get('pack_id')}): {winner.get('id')} "
        f"return_pct={wm.get('total_return_pct')} sharpe={wm.get('sharpe_ratio')} "
        f"engine={winner.get('engine')}"
    )

    comparisons = lb.get("vs_production") or []
    beats = [c for c in comparisons if c.get("beats_production") is True]
    if comparisons:
        lines.append("vs production (same metric, overlap window when available):")
        for c in comparisons:
            flag = "BEATS" if c.get("beats_production") else ("loses" if c.get("beats_production") is False else "n/a")
            lines.append(
                f"  {c['scenario_id']}: {c.get('scenario_value')} vs prod {c.get('production_value')} "
                f"delta={c.get('delta')} ({flag})"
            )

    deploy = "hold — no scenario beat production on overlap with real data"
    if beats:
        deploy = f"shadow-trial candidate(s): {[b['scenario_id'] for b in beats]} — not live until gates pass"
    elif cov == "none":
        prod_ret = (since.get("metrics") or {}).get("total_return_pct")
        win_ret = wm.get("total_return_pct")
        if prod_ret is not None and win_ret is not None:
            lines.append(
                f"Calendar mismatch: production since go-live return_pct={prod_ret} "
                f"vs scenario winner on OHLCV pack window return_pct={win_ret} (not same dates)."
            )
        deploy = (
            "hold — no calendar overlap; use production since-go-live for real P&L; "
            "scenario ranking is OHLCV-only until OHLCV extends into live period"
        )
    lines.append(f"Deployment hint: {deploy}")

    brief = {
        "run_id": lb.get("run_id"),
        "pack_id": lb.get("pack_id"),
        "primary_metric": lb.get("primary_metric"),
        "winner_id": winner.get("id"),
        "winner_return_pct": wm.get("total_return_pct"),
        "production_since_go_live_return_pct": (since.get("metrics") or {}).get("total_return_pct"),
        "overlap_coverage": cov,
        "deployment_hint": deploy,
        "vs_production": comparisons,
    }
    return "\n".join(lines), brief