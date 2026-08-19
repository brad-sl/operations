"""
Format ANALYST-OPT leaderboard + production comparison for daily brief.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
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
    """Returns (console text, brief JSON fragment). Weekly / verbose."""
    lines: List[str] = []
    brief: Dict[str, Any] = {
        "pack_id": lb.get("pack_id"),
        "primary_metric": lb.get("primary_metric"),
        "ranking": lb.get("ranking"),
        "production_coverage": (lb.get("production") or {}).get("coverage"),
        "live_param_audit": lb.get("live_param_audit"),
    }
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
        brief["production_since_go_live"] = {
            "return_pct": sm.get("total_return_pct"),
            "end_equity_usd": sm.get("end_equity_usd"),
            "trade_count": sm.get("trade_count"),
        }

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

    winner = _winner_row(lb)
    wm = winner.get("metrics") or {}
    lines.append(
        f"Scenario winner ({lb.get('pack_id')}): {winner.get('id')} "
        f"return_pct={wm.get('total_return_pct')} sharpe={wm.get('sharpe_ratio')} "
        f"engine={winner.get('engine')}"
    )
    brief["winner"] = {
        "id": winner.get("id"),
        "return_pct": wm.get("total_return_pct"),
        "sharpe": wm.get("sharpe_ratio"),
        "engine": winner.get("engine"),
    }

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
    brief["beats_production"] = [c.get("scenario_id") for c in beats]

    deploy = _deployment_hint_from_leaderboard(lb)
    lines.append(f"Deployment hint: {deploy}")
    brief["deployment_hint"] = deploy

    drift_path = ROOT / "data/state/analyst_shadow_drift_latest.json"
    overlay_path = ROOT / "data/state/analyst_shadow_overlay.json"
    if overlay_path.exists():
        ov = json.loads(overlay_path.read_text())
        if ov.get("active"):
            lines.append(
                f"Shadow overlay ACTIVE: {ov.get('proposal_id')} scenario={ov.get('scenario_id')} "
                f"regime_policy={ov.get('regime_policy', {}).get('enabled')}"
            )
    if drift_path.exists():
        dr = json.loads(drift_path.read_text())
        if dr.get("status") == "active":
            lines.append(
                f"Shadow monitor: live {dr.get('live_return_pct')}% vs pred {dr.get('predicted_return_pct')}% "
                f"ok={dr.get('monitor_ok')}"
            )


    # REGIME-CASH (RC-03)
    try:
        from phase6.core.regime_cash_policy import resolve_regime_cash, persist_status

        snap = resolve_regime_cash()
        persist_status(snap)
        park = "PARK" if (snap.strategy_mode == "usdc_park" or not snap.allow_new_buys) else "DEPLOY"
        lines.append(
            f"REGIME-CASH: {snap.regime} ({park}) util≤{snap.target_max_util_pct:.0%} "
            f"cap=${snap.rebalance_cap_usd:.0f} new_buys={snap.allow_new_buys} "
            f"entry RSI≤{snap.entry.get('max_rsi')} sent≥{snap.entry.get('min_sentiment')} "
            f"btc_30d={snap.btc_return_pct}% enforce={snap.enforce}"
        )
        brief["regime_cash"] = {
            "regime": snap.regime,
            "strategy_mode": snap.strategy_mode,
            "allow_new_buys": snap.allow_new_buys,
            "target_max_util_pct": snap.target_max_util_pct,
            "rebalance_cap_usd": snap.rebalance_cap_usd,
            "btc_return_pct": snap.btc_return_pct,
            "entry": snap.entry,
            "exit": snap.exit,
            "enforce": snap.enforce,
        }
    except Exception as e:
        lines.append(f"REGIME-CASH: unavailable ({e})")

    try:
        from phase6.research.trend_repair import build_trend_repair_status, format_brief_lines, persist_status

        tr = build_trend_repair_status()
        persist_status(tr)
        tr_text, tr_frag = format_brief_lines(tr)
        lines.append(tr_text)
        brief.update(tr_frag)
    except Exception as e:
        lines.append(f"TREND-REPAIR: unavailable ({e})")

    return "\n".join(lines), brief


def _winner_row(lb: Dict[str, Any]) -> Dict[str, Any]:
    if not lb.get("ranking"):
        return (lb.get("scenarios") or [{}])[0] if lb.get("scenarios") else {}
    winner_id = lb["ranking"][0]
    return next((s for s in lb.get("scenarios", []) if s.get("id") == winner_id), {})


def _deployment_hint_from_leaderboard(lb: Dict[str, Any]) -> str:
    prod = lb.get("production") or {}
    cov = prod.get("coverage", "none")
    comparisons = lb.get("vs_production") or []
    beats = [c for c in comparisons if c.get("beats_production") is True]
    if beats:
        return f"shadow-trial candidate(s): {[b['scenario_id'] for b in beats]} — gates still required"
    if cov == "none":
        return (
            "hold — scenario pack is OHLCV-only; trust live since-go-live for P&L until calendar overlap"
        )
    return "hold — no scenario beat production on overlap with real data"


def refresh_live_production_metrics() -> Dict[str, Any]:
    """Recompute production since first trade through today (live ledger)."""
    from phase6.research.production_period_baseline import compute_since_go_live

    return compute_since_go_live()


def build_daily_opt_brief(leaderboard: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """
    Daily brief: fresh live P&L + compact weekly OPT context (frozen leaderboard for scenarios).
    """
    lb = leaderboard or {}
    live = refresh_live_production_metrics()
    lm = live.get("metrics") or {}
    winner = _winner_row(lb)
    wm = winner.get("metrics") or {}
    deploy = _deployment_hint_from_leaderboard(lb) if lb.get("run_id") else "hold — no weekly OPT leaderboard on disk"

    refreshed_at = datetime.now(timezone.utc).isoformat()
    brief: Dict[str, Any] = {
        "run_id": lb.get("run_id"),
        "pack_id": lb.get("pack_id"),
        "leaderboard_generated_at": lb.get("generated_at"),
        "primary_metric": lb.get("primary_metric"),
        "winner_id": winner.get("id"),
        "winner_return_pct": wm.get("total_return_pct"),
        "winner_sharpe": wm.get("sharpe_ratio"),
        "production_since_go_live_return_pct": lm.get("total_return_pct"),
        "production_end_equity_usd": lm.get("end_equity_usd"),
        "production_trade_count": lm.get("trade_count"),
        "production_live_rebalances": lm.get("live_rebalances_executed"),
        "production_refreshed_at": refreshed_at,
        "production_deposit_adjusted": lm.get("deposit_adjusted"),
        "production_net_external_flows_usd": lm.get("net_external_flows_usd"),
        "production_total_return_pct_unadjusted": lm.get("total_return_pct_unadjusted"),
        "production_start_equity_usd": lm.get("start_equity_usd"),
        "overlap_coverage": (lb.get("production") or {}).get("coverage"),
        "deployment_hint": deploy,
        "vs_production": lb.get("vs_production") or [],
    }

    lines: List[str] = []
    lines.append("=== Wealth & scenarios ===")
    if lm.get("total_return_pct") is not None:
        adj_label = " (deposit-adjusted)" if lm.get("deposit_adjusted") else ""
        dep_line = (
            f"Live since go-live: return {lm.get('total_return_pct'):.2f}%{adj_label} | "
            f"equity ${lm.get('end_equity_usd')} | trades {lm.get('trade_count')} | "
            f"rebalances {lm.get('live_rebalances_executed')} "
            f"(refreshed {refreshed_at[:16]}Z)"
        )
        if lm.get("net_external_flows_usd") and abs(float(lm["net_external_flows_usd"])) >= 50:
            dep_line += f" | net deposits ${float(lm['net_external_flows_usd']):,.0f}"
        if lm.get("total_return_pct_unadjusted") is not None and lm.get("deposit_adjusted"):
            u = float(lm["total_return_pct_unadjusted"])
            a = float(lm["total_return_pct"])
            if abs(u - a) > 1.0:
                dep_line += f" | raw NAV Δ {u:.1f}%"
        lines.append(dep_line)
    else:
        lines.append("Live since go-live: no trades in ledger yet.")

    if lb.get("run_id"):
        lines.append(
            f"Weekly OPT `{lb.get('run_id')}` ({(lb.get('generated_at') or '?')[:10]}): "
            f"winner `{winner.get('id')}` sim return {wm.get('total_return_pct')}% "
            f"Sharpe {wm.get('sharpe_ratio')}"
        )
        lines.append(f"Promotion path: {deploy}")
    else:
        lines.append("Weekly OPT: no leaderboard file — run scenario pack when due.")

    overlay_path = ROOT / "data/state/analyst_shadow_overlay.json"
    drift_path = ROOT / "data/state/analyst_shadow_drift_latest.json"
    if overlay_path.exists():
        ov = json.loads(overlay_path.read_text())
        if ov.get("active"):
            lines.append(
                f"Shadow ACTIVE: {ov.get('proposal_id')} / {ov.get('scenario_id')}"
            )
        elif ov.get("last_rollback"):
            rb = ov["last_rollback"]
            lines.append(
                f"Shadow OFF: {rb.get('proposal_id')} rolled back "
                f"{(rb.get('rolled_back_at') or '')[:16]}Z"
            )
    if drift_path.exists():
        dr = json.loads(drift_path.read_text())
        if dr.get("status") == "active":
            lines.append(
                f"Shadow monitor: live {dr.get('live_return_pct')}% vs pred {dr.get('predicted_return_pct')}% "
                f"ok={dr.get('monitor_ok')}"
            )


    # REGIME-CASH (RC-03)
    try:
        from phase6.core.regime_cash_policy import resolve_regime_cash, persist_status

        snap = resolve_regime_cash()
        persist_status(snap)
        park = "PARK" if (snap.strategy_mode == "usdc_park" or not snap.allow_new_buys) else "DEPLOY"
        lines.append(
            f"REGIME-CASH: {snap.regime} ({park}) util≤{snap.target_max_util_pct:.0%} "
            f"cap=${snap.rebalance_cap_usd:.0f} new_buys={snap.allow_new_buys} "
            f"entry RSI≤{snap.entry.get('max_rsi')} sent≥{snap.entry.get('min_sentiment')} "
            f"btc_30d={snap.btc_return_pct}% enforce={snap.enforce}"
        )
        brief["regime_cash"] = {
            "regime": snap.regime,
            "strategy_mode": snap.strategy_mode,
            "allow_new_buys": snap.allow_new_buys,
            "target_max_util_pct": snap.target_max_util_pct,
            "rebalance_cap_usd": snap.rebalance_cap_usd,
            "btc_return_pct": snap.btc_return_pct,
            "entry": snap.entry,
            "exit": snap.exit,
            "enforce": snap.enforce,
        }
    except Exception as e:
        lines.append(f"REGIME-CASH: unavailable ({e})")

    try:
        from phase6.research.trend_repair import build_trend_repair_status, format_brief_lines, persist_status

        tr = build_trend_repair_status()
        persist_status(tr)
        tr_text, tr_frag = format_brief_lines(tr)
        lines.append(tr_text)
        brief.update(tr_frag)
    except Exception as e:
        lines.append(f"TREND-REPAIR: unavailable ({e})")

    return "\n".join(lines), brief