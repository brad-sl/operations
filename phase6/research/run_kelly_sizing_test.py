#!/usr/bin/env python3
"""
ANALYST-KELLY-SIZING-TEST — offline T0/T1/T1b runner.

Real ledger only. No live trading_config / regime_cash_policy writes.
Writes reports/KELLY_SIZING_TEST_<date>.md + .json
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.trade_ledger import TradeLedger
from phase6.research.kelly_sizing import (
    apply_trade_to_equity,
    clamp_to_envelopes,
    estimate_edge_from_returns,
    fractional_kelly,
    kelly_fraction,
    map_risk_fraction_to_deploy_pct,
    risk_budget_to_notional,
)
from phase6.research.production_period_baseline import compute_since_go_live

TRADES_JSONL = ROOT / "trades" / "phase6_trades.jsonl"
CFG_PATH = ROOT / "config" / "trading_config_phase6.json"
REGIME_PATH = ROOT / "config" / "regime_cash_policy.json"
REPORTS = ROOT / "reports"

# Sample gates
MIN_N_FULL = 30
MIN_N_SLICE = 15
MAX_ABS_RETURN = 0.50  # drop cost-basis contaminated outliers (|r|>50%)
MIN_ENTRY_NOTIONAL = 1.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        if "+" not in s[10:] and "Z" not in str(raw):
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def load_config_knobs() -> Dict[str, Any]:
    cfg = json.loads(CFG_PATH.read_text()) if CFG_PATH.exists() else {}
    rm = cfg.get("risk_management") or {}
    wr = cfg.get("withdrawal_reserve") or {}
    regime = json.loads(REGIME_PATH.read_text()) if REGIME_PATH.exists() else {}
    regimes = regime.get("regimes") or {}
    flat_util = float((regimes.get("flat") or {}).get("target_max_util_pct") or 0.65)
    return {
        "deploy_pct": float(rm.get("deploy_pct") or 0.72),
        "stop_loss_pct": float(rm.get("stop_loss_pct") or rm.get("sl_base_pct") or 0.03),
        "min_reserve_usd": float(
            wr.get("min_reserve_usd") or rm.get("min_reserve_usd") or 50.0
        ),
        "max_deployable_usd": wr.get("max_deployable_usd"),
        "regime_flat_target_max_util_pct": flat_util,
        "regimes_util": {
            k: (v or {}).get("target_max_util_pct") for k, v in regimes.items()
        },
        "adaptive_sl": bool(rm.get("adaptive_sl")),
        "sl_min_pct": rm.get("sl_min_pct"),
        "sl_max_pct": rm.get("sl_max_pct"),
    }


def load_closed_sells() -> List[dict]:
    rows: List[dict] = []
    if not TRADES_JSONL.exists():
        return rows
    with open(TRADES_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    out = []
    for r in rows:
        if str(r.get("side") or "").upper() != "SELL":
            continue
        if str(r.get("pair") or "") in {"TEST-USD"}:
            continue
        if str(r.get("signal_source") or "").lower() in {"smoke_test", "test"}:
            continue
        pnl = r.get("pnl")
        if pnl is None:
            continue
        try:
            pf = float(pnl)
        except (TypeError, ValueError):
            continue
        if pf == 0.0:
            continue
        out.append(r)
    return out


def enrich_trade(r: dict) -> Optional[dict]:
    """Implied entry notional from exit*qty - pnl (full close identity)."""
    try:
        q = float(r.get("qty") or 0)
        xp = float(r.get("exit_price") or 0)
        pnl = float(r["pnl"])
    except (TypeError, ValueError, KeyError):
        return None
    if q <= 0 or xp <= 0:
        return None
    exit_n = q * xp
    entry_n = exit_n - pnl
    if entry_n < MIN_ENTRY_NOTIONAL:
        return None
    ret = pnl / entry_n
    ts = _parse_ts(str(r.get("timestamp") or ""))
    return {
        "timestamp": r.get("timestamp"),
        "ts": ts.isoformat() if ts else None,
        "date": ts.date().isoformat() if ts else None,
        "pair": r.get("pair"),
        "pnl": pnl,
        "entry_notional": round(entry_n, 6),
        "exit_notional": round(exit_n, 6),
        "r": ret,
        "signal_source": r.get("signal_source"),
        "abs_r_ok": abs(ret) <= MAX_ABS_RETURN,
    }


def wilson_ci(wins: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = wins / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return round(max(0.0, lo), 4), round(min(1.0, hi), 4)


def edge_table(trades: List[dict], label: str) -> Dict[str, Any]:
    rets = [t["r"] for t in trades]
    base = estimate_edge_from_returns(rets)
    wins = sum(1 for t in trades if t["r"] > 0)
    n = len(trades)
    lo, hi = wilson_ci(wins, n)
    pnls_w = [t["pnl"] for t in trades if t["pnl"] > 0]
    pnls_l = [abs(t["pnl"]) for t in trades if t["pnl"] <= 0]
    b_usd = None
    if pnls_w and pnls_l:
        b_usd = (sum(pnls_w) / len(pnls_w)) / (sum(pnls_l) / len(pnls_l))
    insufficient = bool(base.get("insufficient")) or n < MIN_N_FULL
    if label != "full_plausible" and n >= MIN_N_SLICE and not base.get("insufficient"):
        # slices can be smaller
        insufficient = n < MIN_N_SLICE
    return {
        "label": label,
        **base,
        "p_wilson_95": {"low": lo, "high": hi},
        "b_usd_avg_win_loss": round(b_usd, 6) if b_usd is not None else None,
        "sum_pnl_usd": round(sum(t["pnl"] for t in trades), 4),
        "insufficient_for_recommend": insufficient,
        "min_n_gate": MIN_N_FULL if label.startswith("full") else MIN_N_SLICE,
    }


def max_drawdown(equity_path: List[float]) -> float:
    if not equity_path:
        return 0.0
    peak = equity_path[0]
    max_dd = 0.0
    for e in equity_path:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def simulate_path(
    returns: List[float],
    f_risk: float,
    sl_pct: float,
    start_equity: float,
    envelopes: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    eq = float(start_equity)
    path = [eq]
    pnls = []
    bindings = {}
    ruined = False
    reserve = float(envelopes.get("min_reserve_usd") or 0)
    for r in returns:
        if eq <= reserve:
            ruined = True
            break
        step = apply_trade_to_equity(eq, r, f_risk, sl_pct, envelopes)
        eq = step["equity_after"]
        path.append(eq)
        pnls.append(step["pnl"])
        b = step["binding"]
        bindings[b] = bindings.get(b, 0) + 1
        if eq <= 0:
            ruined = True
            eq = 0.0
            break
    end = path[-1]
    growth = (end / start_equity - 1.0) if start_equity > 0 else None
    return {
        "label": label,
        "f_risk": f_risk,
        "start_equity": start_equity,
        "end_equity": round(end, 4),
        "growth_pct": round(100.0 * growth, 4) if growth is not None else None,
        "max_dd_pct": round(100.0 * max_drawdown(path), 4),
        "n_steps": len(pnls),
        "sum_pnl": round(sum(pnls), 4),
        "near_reserve_or_ruin": ruined or end <= reserve * 1.05,
        "binding_counts": bindings,
        "final_equity_vs_reserve": round(end - reserve, 4),
    }


def baseline_risk_fraction(deploy_pct: float, sl_pct: float, per_trade_risk: float = 0.01) -> Dict[str, Any]:
    """
    Live stack does not size from Kelly. Approximate risk lenses:
      - per_trade_risk_language: 1% equity at risk (common wording)
      - book_sl_if_full_deploy: deploy_pct * sl_pct (all notionals stop out together)
    Path baseline uses per_trade_risk_language as primary sequential proxy.
    """
    return {
        "per_trade_risk_language": per_trade_risk,
        "book_simultaneous_sl_if_deployed": round(deploy_pct * sl_pct, 6),
        "deploy_pct": deploy_pct,
        "sl_pct": sl_pct,
        "path_baseline_f": per_trade_risk,
    }


def choose_recommendation(
    edge: Dict[str, Any],
    paths: Dict[str, Dict[str, Any]],
    half_f: float,
    recent_edge: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Enum for trial_cycle decide (proposal only):
      drop | continue_observe_only | propose_scoped_shadow_experiment | extend_trial

    Shadow only if haircutted half/quarter beats baseline on DD-adjusted growth
    AND does not worsen max DD by >2pp AND recent window is not clearly negative-edge.
    """
    if edge.get("insufficient_for_recommend") or edge.get("insufficient"):
        return {
            "enum": "continue_observe_only",
            "go_shadow": False,
            "reason": "insufficient_or_weak_edge_sample",
        }
    f_full = float(edge.get("f_full") or 0)
    if f_full <= 0:
        return {
            "enum": "drop",
            "go_shadow": False,
            "reason": "non_positive_kelly_edge_on_plausible_ledger",
        }

    recent_edge = recent_edge or {}
    recent_n = int(recent_edge.get("n") or 0)
    recent_f = recent_edge.get("f_full")
    recent_neg = (
        recent_n >= MIN_N_SLICE
        and recent_f is not None
        and float(recent_f) <= 0
    )

    base = paths.get("baseline_1pct_risk") or {}
    half = paths.get("half_kelly_capped") or {}
    quarter = paths.get("quarter_kelly_capped") or {}
    full = paths.get("full_kelly_capped") or {}

    def score(p: Dict[str, Any]) -> float:
        # growth percentage points minus 0.5 * max_dd percentage points
        g = float(p.get("growth_pct") or 0)
        dd = float(p.get("max_dd_pct") or 0)
        return g - 0.5 * dd

    base_s, half_s, q_s = score(base), score(half), score(quarter)
    half_dd = float(half.get("max_dd_pct") or 99)
    base_dd = float(base.get("max_dd_pct") or 99)
    q_dd = float(quarter.get("max_dd_pct") or 99)
    full_dd = float(full.get("max_dd_pct") or 99)
    scores = {
        "baseline": round(base_s, 4),
        "half": round(half_s, 4),
        "quarter": round(q_s, 4),
        "half_dd": half_dd,
        "base_dd": base_dd,
        "quarter_dd": q_dd,
        "full_dd": full_dd,
    }

    if recent_neg:
        return {
            "enum": "drop",
            "go_shadow": False,
            "reason": (
                f"recent window n={recent_n} has non-positive Kelly "
                f"(f_full={recent_f}, p={recent_edge.get('p')}); "
                f"full-sample f_full={f_full:.4f} is unstable / regime-shifted. "
                f"Path DD: half={half_dd:.1f}% vs baseline={base_dd:.1f}%."
            ),
            "scores": scores,
        }

    # Full Kelly path is diagnostic only — never promote
    if half_s > base_s + 1.0 and half_dd <= base_dd + 2.0 and half_f > 0:
        return {
            "enum": "propose_scoped_shadow_experiment",
            "go_shadow": True,
            "preferred_fraction": "half_kelly",
            "reason": (
                f"half-Kelly capped DD-adj score {half_s:.2f} > baseline {base_s:.2f} "
                f"with maxDD {half_dd:.2f}% vs {base_dd:.2f}%"
            ),
            "scores": scores,
        }
    if q_s > base_s + 1.0 and q_dd <= base_dd + 2.0:
        return {
            "enum": "propose_scoped_shadow_experiment",
            "go_shadow": True,
            "preferred_fraction": "quarter_kelly",
            "reason": (
                f"quarter-Kelly capped score {q_s:.2f} > baseline {base_s:.2f}"
            ),
            "scores": scores,
        }

    # Growth may look better but DD worse, or edge too thin → no shadow
    if half_dd > base_dd + 2.0 or q_dd > base_dd + 2.0:
        return {
            "enum": "drop",
            "go_shadow": False,
            "reason": (
                f"Kelly-capped paths worsen max DD (half {half_dd:.1f}% / "
                f"quarter {q_dd:.1f}% vs baseline {base_dd:.1f}%) even when "
                f"growth is higher; envelopes bind full≈half "
                f"(diagnostic full DD={full_dd:.1f}%). No shadow."
            ),
            "scores": scores,
        }

    if f_full < 0.05 or half_s <= base_s:
        return {
            "enum": "drop",
            "go_shadow": False,
            "reason": (
                f"edge f_full={f_full:.4f} but capped Kelly paths do not beat baseline "
                f"on DD-adjusted growth (half={half_s:.2f} vs base={base_s:.2f})"
            ),
            "scores": scores,
        }

    return {
        "enum": "continue_observe_only",
        "go_shadow": False,
        "reason": "marginal; collect more clean closed trades before shadow",
        "scores": scores,
    }


def run() -> Dict[str, Any]:
    knobs = load_config_knobs()
    sl = knobs["stop_loss_pct"]
    deploy = knobs["deploy_pct"]
    util = knobs["regime_flat_target_max_util_pct"]
    reserve = knobs["min_reserve_usd"]

    raw_sells = load_closed_sells()
    enriched = []
    dropped_outlier = 0
    dropped_enrich = 0
    for r in raw_sells:
        e = enrich_trade(r)
        if e is None:
            dropped_enrich += 1
            continue
        if not e["abs_r_ok"]:
            dropped_outlier += 1
            continue
        enriched.append(e)

    enriched.sort(key=lambda t: t.get("ts") or "")

    full_edge = edge_table(enriched, "full_plausible")
    # July 2026+ slice (recent regime)
    july = [t for t in enriched if (t.get("date") or "") >= "2026-07-01"]
    july_edge = edge_table(july, "since_2026-07-01") if july else {
        "label": "since_2026-07-01",
        "n": 0,
        "insufficient_for_recommend": True,
    }

    # Pair slices if n allows
    by_pair: Dict[str, List[dict]] = {}
    for t in enriched:
        by_pair.setdefault(str(t.get("pair") or "?"), []).append(t)
    pair_edges = []
    for pair, ts_ in sorted(by_pair.items(), key=lambda kv: -len(kv[1])):
        if len(ts_) >= MIN_N_SLICE:
            pair_edges.append(edge_table(ts_, f"pair:{pair}"))

    p = full_edge.get("p")
    b = full_edge.get("b")
    f_full = kelly_fraction(p or 0, b or 0) if p is not None and b is not None else 0.0
    f_half = fractional_kelly(p or 0, b or 0, 0.5) if p and b else 0.0
    f_quarter = fractional_kelly(p or 0, b or 0, 0.25) if p and b else 0.0

    # Multi-asset haircut on risk fraction for sizing map (document concurrent book)
    multi_haircut = 0.5
    f_half_eff = f_half * multi_haircut
    f_quarter_eff = f_quarter * multi_haircut
    f_full_eff = f_full * multi_haircut

    base_f = baseline_risk_fraction(deploy, sl)
    prod = compute_since_go_live()
    metrics = (prod or {}).get("metrics") or {}
    start_eq = float(metrics.get("start_equity_usd") or metrics.get("initial_capital") or 1000.0)
    end_eq_live = metrics.get("end_equity_usd")

    envelopes = {
        "deploy_pct": deploy,
        "regime_target_max_util_pct": util,
        "min_reserve_usd": reserve,
        "max_position_usd": float(knobs["max_deployable_usd"])
        if knobs.get("max_deployable_usd")
        else None,
        "rebalance_cap_usd": None,
        "cash_usd": None,  # apply_trade defaults cash=equity each step (sequential abstraction)
    }

    returns = [t["r"] for t in enriched]
    paths = {
        "baseline_1pct_risk": simulate_path(
            returns, base_f["path_baseline_f"], sl, start_eq, envelopes, "baseline_1pct_risk"
        ),
        "full_kelly_capped": simulate_path(
            returns, f_full_eff, sl, start_eq, envelopes, "full_kelly_capped"
        ),
        "half_kelly_capped": simulate_path(
            returns, f_half_eff, sl, start_eq, envelopes, "half_kelly_capped"
        ),
        "quarter_kelly_capped": simulate_path(
            returns, f_quarter_eff, sl, start_eq, envelopes, "quarter_kelly_capped"
        ),
        # Unhaircut half for sensitivity (still envelope-clamped)
        "half_kelly_no_multi_haircut": simulate_path(
            returns, f_half, sl, start_eq, envelopes, "half_kelly_no_multi_haircut"
        ),
    }

    # Example clamp at current end equity
    eq_now = float(end_eq_live or start_eq)
    example_raw = risk_budget_to_notional(f_half_eff, eq_now, sl)
    example_clamp = clamp_to_envelopes(
        example_raw,
        equity=eq_now,
        f_requested=f_half_eff,
        deploy_pct=deploy,
        regime_target_max_util_pct=util,
        min_reserve_usd=reserve,
        max_position_usd=float(knobs["max_deployable_usd"])
        if knobs.get("max_deployable_usd")
        else None,
        cash_usd=eq_now * (1 - 0.5),  # assume half already in risk assets
        already_deployed_usd=eq_now * 0.5,
    )

    deploy_map_half = map_risk_fraction_to_deploy_pct(
        f_half_eff, sl, haircut=1.0, deploy_cap=0.95
    )
    # Note: multi haircut already in f_half_eff; map is notional fraction of book

    rec = choose_recommendation(full_edge, paths, f_half_eff, recent_edge=july_edge)

    shadow = None
    if rec.get("go_shadow"):
        preferred = rec.get("preferred_fraction") or "half_kelly"
        f_use = f_half_eff if "half" in preferred else f_quarter_eff
        shadow = {
            "status": "proposed_only",
            "overlay_sketch": {
                "proposal_id": f"ANALYST-{date.today().strftime('%Y%m%d')}-KELLY-001",
                "scenario_id": "kelly_fractional_risk_budget",
                "live_overlay": {
                    # Prefer risk_usd semantics; deploy_pct map is secondary lens
                    "risk_management.deploy_pct": round(min(deploy_map_half, 0.78), 4),
                    "note": (
                        "Shadow only — do not write trading_config. "
                        "Primary concept is risk fraction f, not notional deploy_pct."
                    ),
                },
                "risk_fraction_effective": round(f_use, 6),
                "sl_pct": sl,
                "multi_asset_haircut": multi_haircut,
                "eval_command": (
                    "PYTHONPATH=. python3 phase6/research/run_kelly_sizing_test.py"
                ),
                "sibling_pattern": "phase6/research/run_deploy_pct_shadow_eval.py",
            },
        }
    else:
        shadow = {"status": "no_go", "overlay_sketch": None}

    # Isolation self-check inline
    iso = {
        "article_f": kelly_fraction(0.55, 2.0),
        "article_half": fractional_kelly(0.55, 2.0, 0.5),
    }

    report = {
        "report_id": f"KELLY_SIZING_TEST_{date.today().isoformat()}",
        "trial_id": "ANALYST-KELLY-SIZING-TEST-20260721-TRIAL",
        "master_id": "ANALYST-KELLY-SIZING-TEST-20260721",
        "generated_at": _utc_now(),
        "real_data_only": True,
        "live_config_writes": False,
        "knobs_baseline": knobs,
        "isolation_check": iso,
        "data_quality": {
            "raw_nonzero_pnl_sells": len(raw_sells),
            "enriched_plausible": len(enriched),
            "dropped_enrich_fail": dropped_enrich,
            "dropped_abs_r_gt": MAX_ABS_RETURN,
            "dropped_outlier_count": dropped_outlier,
            "max_abs_return_filter": MAX_ABS_RETURN,
            "min_entry_notional_usd": MIN_ENTRY_NOTIONAL,
            "return_definition": "r = pnl / (qty*exit_price - pnl)  # implied entry notional",
            "notes": [
                "Some ledger rows have placeholder entry_price (e.g. 100/65000); "
                "implied notional identity used; |r|>50% dropped as cost-basis contamination.",
                "Single-bet Kelly overstates safe f on multi-asset correlated books — "
                f"applied multi_asset_haircut={multi_haircut} on path risk fractions.",
                "Sequential path replay is an offline proxy, not concurrent portfolio truth.",
            ],
        },
        "edge": {
            "full_plausible": full_edge,
            "since_2026_07_01": july_edge,
            "pair_slices": pair_edges,
            "f_full": round(f_full, 6),
            "f_half": round(f_half, 6),
            "f_quarter": round(f_quarter, 6),
            "f_half_effective_haircut": round(f_half_eff, 6),
            "f_quarter_effective_haircut": round(f_quarter_eff, 6),
            "f_full_effective_haircut": round(f_full_eff, 6),
            "multi_asset_haircut": multi_haircut,
        },
        "baseline_risk_lenses": base_f,
        "production_live": {
            "start_equity_usd": start_eq,
            "end_equity_usd": end_eq_live,
            "total_return_pct_deposit_adj": metrics.get("total_return_pct"),
            "trade_count": metrics.get("trade_count"),
            "realized_pnl_usd": metrics.get("realized_pnl_usd"),
        },
        "path_compare": paths,
        "example_half_kelly_clamp_at_end_equity": example_clamp.to_dict(),
        "deploy_pct_map_from_half_eff": {
            "candidate_deploy_pct": round(deploy_map_half, 4),
            "live_deploy_pct": deploy,
            "interpretation": (
                "Notional deploy_pct ≈ f_risk/sl after haircut; "
                "distinct from risk fraction. Do not set live without Brad+gates."
            ),
        },
        "recommendation": rec,
        "shadow": shadow,
        "honest_assessment": {
            "sample_n": full_edge.get("n"),
            "p": full_edge.get("p"),
            "b": full_edge.get("b"),
            "p_ci_95": full_edge.get("p_wilson_95"),
            "recent_july_edge_negative": bool(
                (july_edge.get("f_full") or 0) <= 0 or (july_edge.get("p") or 0) < 0.35
            ),
            "estimation_error_trap": (
                "Small n and contaminated basis make p,b unstable; "
                "half-Kelly still large if p overestimated — prefer quarter + hard caps."
            ),
            "notional_vs_risk": (
                "Live runner sizes BUY as cash*weight*deploy_pct (notional), not "
                "loss-at-stop. Kelly f must map through /sl_pct then clamp — "
                "engineer follow-on if executor still conflates 1% notional with 1% risk."
            ),
            "correlation_gap": (
                "Path model is sequential independent bets; live book is concurrent "
                "and correlated — haircut 0.5 is a blunt prior, not estimated Σ."
            ),
            "full_kelly_live": "REJECT — never recommend as live default.",
        },
    }
    return report


def write_reports(report: Dict[str, Any]) -> Tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    json_path = REPORTS / f"KELLY_SIZING_TEST_{day}.json"
    md_path = REPORTS / f"KELLY_SIZING_TEST_{day}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))

    e = report["edge"]["full_plausible"]
    rec = report["recommendation"]
    paths = report["path_compare"]
    lines = [
        f"# Kelly Sizing Test — {day}",
        "",
        f"**Trial:** `{report['trial_id']}`  ",
        f"**Master:** `{report['master_id']}`  ",
        f"**Generated:** {report['generated_at']}  ",
        f"**Real data only:** {report['real_data_only']}  ",
        f"**Live config writes:** {report['live_config_writes']}",
        "",
        "## Executive summary",
        "",
        f"- Closed sells (plausible \\(r\\)): **n={e.get('n')}**  "
        f"(raw nonzero PnL sells={report['data_quality']['raw_nonzero_pnl_sells']}, "
        f"outliers dropped={report['data_quality']['dropped_outlier_count']})",
        f"- Edge: **p={e.get('p')}** (Wilson 95% {e.get('p_wilson_95')}), "
        f"**b={e.get('b')}** (mean win r / mean |loss r|)",
        f"- Kelly: **f_full={report['edge']['f_full']}**, "
        f"**f_half={report['edge']['f_half']}**, "
        f"**f_quarter={report['edge']['f_quarter']}**",
        f"- After multi-asset haircut {report['edge']['multi_asset_haircut']}: "
        f"f_half_eff={report['edge']['f_half_effective_haircut']}, "
        f"f_quarter_eff={report['edge']['f_quarter_effective_haircut']}",
        f"- **Recommendation enum:** `{rec.get('enum')}`  ",
        f"- **Shadow go?** **{rec.get('go_shadow')}** — {rec.get('reason')}",
        f"- Full Kelly as live default: **REJECT**",
        "",
        "## Tier 0 — isolation",
        "",
        f"- Article 55%/2:1 → f_full={report['isolation_check']['article_f']} "
        f"(expect 0.325), half={report['isolation_check']['article_half']} (expect 0.1625)",
        "- Module: `phase6/research/kelly_sizing.py`",
        "- Tests: `PYTHONPATH=. python3 phase6/research/test_isolation_kelly_sizing.py`",
        "",
        "## Tier 1 — ledger edge",
        "",
        "Return definition: `r = pnl / (qty * exit_price - pnl)` (implied entry notional).",
        f"Filter: `|r| <= {report['data_quality']['max_abs_return_filter']}`, "
        f"entry notional >= ${report['data_quality']['min_entry_notional_usd']}.",
        "",
        "### Full plausible sample",
        "",
        "```json",
        json.dumps(e, indent=2),
        "```",
        "",
        "### Since 2026-07-01",
        "",
        "```json",
        json.dumps(report["edge"]["since_2026_07_01"], indent=2),
        "```",
        "",
        "### Pair slices (n ≥ 15)",
        "",
        "```json",
        json.dumps(report["edge"]["pair_slices"], indent=2),
        "```",
        "",
        "## Tier 1b — offline path compare",
        "",
        "Sequential single-bet proxy on the same plausible return sequence. "
        "Envelopes: live deploy_pct / flat regime util / min reserve. "
        "Kelly paths use **haircutted** f. Baseline uses **1% equity risk language** per trade.",
        "",
        "| Path | f_risk | End equity | Growth % | Max DD % | Near reserve |",
        "|------|--------|------------|----------|----------|--------------|",
    ]
    for key in [
        "baseline_1pct_risk",
        "quarter_kelly_capped",
        "half_kelly_capped",
        "half_kelly_no_multi_haircut",
        "full_kelly_capped",
    ]:
        pth = paths[key]
        lines.append(
            f"| {key} | {pth['f_risk']:.6f} | {pth['end_equity']} | "
            f"{pth['growth_pct']} | {pth['max_dd_pct']} | {pth['near_reserve_or_ruin']} |"
        )
    lines += [
        "",
        "### Production live (deposit-adjusted context)",
        "",
        "```json",
        json.dumps(report["production_live"], indent=2),
        "```",
        "",
        "## Risk fraction vs notional deploy_pct",
        "",
        f"- Live `deploy_pct`={report['knobs_baseline']['deploy_pct']} "
        f"(notional budget on cash/equity), SL={report['knobs_baseline']['stop_loss_pct']}",
        f"- Book simultaneous SL if fully deployed ≈ "
        f"{report['baseline_risk_lenses']['book_simultaneous_sl_if_deployed']}",
        f"- Map half-eff f → candidate deploy_pct ≈ "
        f"{report['deploy_pct_map_from_half_eff']['candidate_deploy_pct']} "
        f"({report['deploy_pct_map_from_half_eff']['interpretation']})",
        "",
        "```json",
        json.dumps(report["example_half_kelly_clamp_at_end_equity"], indent=2),
        "```",
        "",
        "## Tier 2 — shadow",
        "",
        "```json",
        json.dumps(report["shadow"], indent=2),
        "```",
        "",
        "## Honest assessment",
        "",
        "```json",
        json.dumps(report["honest_assessment"], indent=2),
        "```",
        "",
        "## Decide (Brad)",
        "",
        "```bash",
        f"python3 phase6/research/trial_cycle.py decide {report['trial_id']} {rec.get('enum')} --note 'see reports/{json_path.name}'",
        "```",
        "",
        "## Files",
        "",
        f"- `{json_path.relative_to(ROOT)}`",
        f"- `{md_path.relative_to(ROOT)}`",
        "- `phase6/research/kelly_sizing.py`",
        "- `phase6/research/test_isolation_kelly_sizing.py`",
        "- `phase6/research/run_kelly_sizing_test.py`",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n")
    return md_path, json_path


def main() -> int:
    report = run()
    md_path, json_path = write_reports(report)
    print(json.dumps({
        "md": str(md_path),
        "json": str(json_path),
        "n": report["edge"]["full_plausible"].get("n"),
        "p": report["edge"]["full_plausible"].get("p"),
        "b": report["edge"]["full_plausible"].get("b"),
        "f_full": report["edge"]["f_full"],
        "f_half": report["edge"]["f_half"],
        "recommendation": report["recommendation"].get("enum"),
        "go_shadow": report["recommendation"].get("go_shadow"),
    }, indent=2))
    print(f"\nWrote {md_path}\nWrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
