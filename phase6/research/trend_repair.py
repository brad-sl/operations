"""Trend repair snapshot — deposit-adjusted equity path diagnosis for Analyst loop.

Canonical doc: docs/TREND_REPAIR_PLAYBOOK.md

Writes data/state/trend_repair_status.json. No capital moves. No auto-promote.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUS_PATH = ROOT / "data" / "state" / "trend_repair_status.json"
LIVE_STATE = ROOT / "data" / "state" / "phase6_live_state.json"
REGIME_STATUS = ROOT / "data" / "state" / "regime_cash_status.json"
DB_PATH = ROOT / "data" / "phase6.db"
PLAYBOOK = "docs/TREND_REPAIR_PLAYBOOK.md"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _open_book_drag(live: Dict[str, Any]) -> Dict[str, Any]:
    positions = live.get("trading_positions") or live.get("positions") or []
    try:
        from phase6.core.position_cost_basis import recompute_trading_positions_pnl

        positions = recompute_trading_positions_pnl(list(positions))
    except Exception:
        pass
    rows: List[Dict[str, Any]] = []
    for p in positions:
        pair = str(p.get("pair") or "")
        if pair in ("USD", "USDC", ""):
            continue
        val = float(p.get("value_usd") or p.get("notional_usd") or 0.0)
        if val < 1.0:
            continue
        upct = p.get("unrealized_pnl_pct")
        try:
            upct_f = float(upct) if upct is not None else 0.0
        except (TypeError, ValueError):
            upct_f = 0.0
        # normalize fraction vs percent
        if abs(upct_f) <= 2.0 and upct_f != 0.0:
            upct_disp = upct_f * 100.0
        else:
            upct_disp = upct_f
        uusd = p.get("unrealized_pnl_usd")
        try:
            uusd_f = float(uusd) if uusd is not None else val * (upct_disp / 100.0)
        except (TypeError, ValueError):
            uusd_f = 0.0
        rows.append(
            {
                "pair": pair,
                "value_usd": round(val, 2),
                "unrealized_pnl_pct": round(upct_disp, 2),
                "unrealized_pnl_usd": round(uusd_f, 2),
            }
        )
    rows.sort(key=lambda r: r["unrealized_pnl_usd"])
    worst = rows[:5]
    best = sorted(rows, key=lambda r: -r["unrealized_pnl_usd"])[:3]
    return {
        "n_positions": len(rows),
        "sum_unrealized_usd": round(sum(r["unrealized_pnl_usd"] for r in rows), 2),
        "worst": worst,
        "best": best,
    }


def _util_and_cash(live: Dict[str, Any]) -> Dict[str, float]:
    total = float(live.get("total_usd") or live.get("total_balance") or 0.0)
    holdings = live.get("total_holdings_value")
    if holdings is None:
        cash = float(live.get("cash_usd") or live.get("cash_balance") or 0.0)
        holdings = max(0.0, total - cash) if total else 0.0
    else:
        holdings = float(holdings)
        cash = float(live.get("cash_usd") or live.get("cash_balance") or max(0.0, total - holdings))
    util = (holdings / total) if total > 0 else 0.0
    return {
        "total_usd": round(total, 2),
        "cash_usd": round(cash, 2),
        "holdings_usd": round(float(holdings), 2),
        "util": round(util, 4),
    }


def _primary_layer(
    *,
    health_state: str,
    park: bool,
    util: float,
    target_util: Optional[float],
    open_sum_u: float,
    window_ret: Optional[float],
    recent_ret: Optional[float],
) -> Tuple[str, str]:
    """Return (layer, detail)."""
    util_gap = None
    if target_util is not None and park:
        util_gap = util - float(target_util)

    if park and util_gap is not None and util_gap > 0.12:
        tgt = float(target_util) if target_util is not None else 0.0
        return (
            "open_book",
            f"Park on but util {util:.0%} ≫ target {tgt:.0%}; residual MTM drives path (open_sum_u={open_sum_u}).",
        )
    if park and open_sum_u < -15:
        return (
            "open_book",
            f"Park on; open book unrealized {open_sum_u} USD dominates near-term path.",
        )
    if (
        recent_ret is not None
        and window_ret is not None
        and recent_ret > window_ret + 3
        and health_state in ("declining", "soft_down")
    ):
        return (
            "churn_or_legacy_drawdown",
            "Recent path better than full window — legacy damage still in slope; avoid re-opening churn.",
        )
    if not park and health_state in ("declining", "soft_down"):
        return (
            "edge_or_entries",
            "Deploy allowed but path still down — test entries/exits/overlap before loosening gates.",
        )
    if health_state in ("recovering", "stabilizing_up"):
        return (
            "hold_course",
            "Path improving — keep Tier 0 integrity; do not overfit one green stretch.",
        )
    return (
        "regime_or_mixed",
        "Mixed/sideways — maintain gates; Analyst digs regime label + fee/edge only with evidence clocks.",
    )


def _tier_recommendations(
    *,
    layer: str,
    park: bool,
    regime: str,
    util: float,
    target_util: Optional[float],
    health: Dict[str, Any],
    open_book: Dict[str, Any],
    recent_ret: Optional[float],
    slope: Optional[float],
) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    # Tier 0 always
    recs.append(
        {
            "tier": 0,
            "action": "preserve_gate_integrity",
            "detail": (
                "Keep enforce=true REGIME-CASH path; no force_rebalance/cash-hold clear; "
                "no enforce:false thaw; SELLs allowed. See TREND_REPAIR_PLAYBOOK §4 Tier 0."
            ),
            "auto_apply": False,
            "priority": "P0",
        }
    )
    if park:
        recs.append(
            {
                "tier": 0,
                "action": "keep_park_buys_blocked",
                "detail": f"Regime {regime}: block new BUYs while park; do not treat pair RSI heat as portfolio risk-on.",
                "auto_apply": False,
                "priority": "P0",
            }
        )

    if layer == "open_book" or (park and target_util is not None and util > float(target_util) + 0.08):
        worst = open_book.get("worst") or []
        names = ", ".join(f"{w['pair']} ({w['unrealized_pnl_pct']}%)" for w in worst[:3]) or "n/a"
        recs.append(
            {
                "tier": 1,
                "action": "rules_based_inventory_util_glide",
                "detail": (
                    f"Glide util toward target {target_util} via exit-knob SELLs (not lottery trims). "
                    f"Soft names now: {names}. Platform form: policy exit section + proposal template."
                ),
                "metric_targets": {
                    "util_gap_to_target": "shrink",
                    "recent_return_pct": "≥ 0 over 14d",
                    "slope_pct_per_day": "less negative over 14d",
                },
                "evidence_days_min": 14,
                "auto_apply": False,
                "priority": "P1",
            }
        )

    # Tier 2 only as proposal stub when clocks not met
    slope_ok = slope is not None and slope > 0
    recent_ok = recent_ret is not None and recent_ret >= 0
    if park and regime in ("transition", "flat"):
        ready = bool(slope_ok and recent_ok)
        recs.append(
            {
                "tier": 2,
                "action": "gated_micro_deploy_experiment",
                "detail": (
                    "Template: flat option B (small cap + strict RSI/sentiment) on BOTH policy + knob_map. "
                    "Transition micro-cap only after evidence clocks. Never enforce:false."
                    if not ready
                    else "Evidence clocks green enough to *design* Tier 2 patch — still no auto-apply; shadow/tiny cap first."
                ),
                "ready_to_design": ready,
                "evidence_days_min": 14,
                "auto_apply": False,
                "priority": "P2",
            }
        )

    recs.append(
        {
            "tier": 3,
            "action": "analyst_opt_overlap_and_gates",
            "detail": (
                "Weekly OPT / regime sweep / scenario overlap vs production; promote only if "
                "live_param_audit clean + real overlap + operator apply. Score return AND less loss."
            ),
            "auto_apply": False,
            "priority": "P1",
        }
    )
    return recs


def build_trend_repair_status(
    *,
    days: int = 30,
    max_points: int = 48,
    timeout: float = 6.0,
) -> Dict[str, Any]:
    from phase6.core.dashboard_serve_helpers import compute_equity_trend

    live = _load_json(LIVE_STATE)
    regime = _load_json(REGIME_STATUS)
    book = _util_and_cash(live)
    total = book["total_usd"] or float(live.get("total_usd") or 0.0)
    eq = compute_equity_trend(
        total if total > 0 else 1.0,
        DB_PATH,
        days=days,
        max_points=max_points,
        timeout=timeout,
    )
    open_book = _open_book_drag(live)
    health = eq.get("health") or {}
    trend = eq.get("trend") or {}
    window_ret = eq.get("window_return_pct")
    recent_ret = eq.get("recent_return_pct")
    slope = trend.get("slope_pct_per_day")
    park = bool(
        str(regime.get("strategy_mode") or "") == "usdc_park"
        or regime.get("allow_new_buys") is False
    )
    target_util = regime.get("target_max_util_pct")
    try:
        target_util_f = float(target_util) if target_util is not None else None
    except (TypeError, ValueError):
        target_util_f = None

    layer, layer_detail = _primary_layer(
        health_state=str(health.get("state") or ""),
        park=park,
        util=float(book["util"]),
        target_util=target_util_f,
        open_sum_u=float(open_book.get("sum_unrealized_usd") or 0),
        window_ret=window_ret if isinstance(window_ret, (int, float)) else None,
        recent_ret=recent_ret if isinstance(recent_ret, (int, float)) else None,
    )

    # path segments (coarse) for analyst narrative
    pts = eq.get("points") or []
    segments: List[Dict[str, Any]] = []
    if len(pts) >= 4:
        last_day = float(pts[-1].get("day") or 0)
        cuts = [0.0, max(0.0, last_day - 21), max(0.0, last_day - 14), max(0.0, last_day - 7), last_day + 0.01]
        labels = ["older", "d21_14", "d14_7", "last7"]
        for i, lab in enumerate(labels):
            a, b = cuts[i], cuts[i + 1]
            seg = [p for p in pts if a <= float(p.get("day") or 0) < b]
            if len(seg) < 2:
                continue
            i0, i1 = float(seg[0]["index"]), float(seg[-1]["index"])
            segments.append(
                {
                    "label": lab,
                    "day0": seg[0].get("day"),
                    "day1": seg[-1].get("day"),
                    "index0": seg[0].get("index"),
                    "index1": seg[-1].get("index"),
                    "return_pct": round((i1 / i0 - 1.0) * 100.0, 2) if i0 else None,
                }
            )

    recs = _tier_recommendations(
        layer=layer,
        park=park,
        regime=str(regime.get("regime") or "unknown"),
        util=float(book["util"]),
        target_util=target_util_f,
        health=health,
        open_book=open_book,
        recent_ret=recent_ret if isinstance(recent_ret, (int, float)) else None,
        slope=slope if isinstance(slope, (int, float)) else None,
    )

    evidence = {
        "observe_recent_vs_window_days": 7,
        "claim_stabilizing_min_days": 14,
        "claim_recovering_or_tier2_design_min_days": 14,
        "widen_caps_min_days": 28,
        "note": "Do not promote Tier 2 on one week of smoother path alone.",
    }

    status: Dict[str, Any] = {
        "schema": "trend_repair_status_v1",
        "playbook": PLAYBOOK,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "auto_promote": False,
        "equity_trend": {
            "status": eq.get("status"),
            "days": eq.get("days"),
            "point_count": eq.get("point_count"),
            "window_return_pct": window_ret,
            "recent_return_pct": recent_ret,
            "trend": trend,
            "health": health,
            # keep path light for status file
            "points_tail": (pts[-8:] if pts else []),
        },
        "path_segments": segments,
        "capital": book,
        "regime": {
            "regime": regime.get("regime"),
            "strategy_mode": regime.get("strategy_mode"),
            "allow_new_buys": regime.get("allow_new_buys"),
            "rebalance_cap_usd": regime.get("rebalance_cap_usd"),
            "target_max_util_pct": regime.get("target_max_util_pct"),
            "btc_return_pct": regime.get("btc_return_pct")
            or (regime.get("detector") or {}).get("btc_return_pct"),
            "enforce": regime.get("enforce"),
            "label": regime.get("label"),
        },
        "open_book": open_book,
        "diagnosis": {
            "primary_layer": layer,
            "detail": layer_detail,
            "health_state": health.get("state"),
            "health_label": health.get("label"),
            "health_blurb": health.get("blurb"),
        },
        "recommendations": recs,
        "evidence_clocks": evidence,
        "operator_summary": _operator_summary(health, window_ret, recent_ret, slope, layer, park, book, target_util_f),
    }
    return status


def _operator_summary(
    health: Dict[str, Any],
    window_ret: Any,
    recent_ret: Any,
    slope: Any,
    layer: str,
    park: bool,
    book: Dict[str, float],
    target_util: Optional[float],
) -> str:
    h = health.get("label") or health.get("state") or "n/a"
    wr = f"{window_ret:+.2f}%" if isinstance(window_ret, (int, float)) else "n/a"
    rr = f"{recent_ret:+.2f}%" if isinstance(recent_ret, (int, float)) else "n/a"
    sl = f"{slope:+.3f}/d" if isinstance(slope, (int, float)) else "n/a"
    park_s = "PARK" if park else "deploy-capable"
    util_s = f"util {book.get('util', 0):.0%}"
    if target_util is not None:
        util_s += f" (target ≤{float(target_util):.0%})"
    return (
        f"TREND-REPAIR: {h} | window {wr} | recent {rr} | slope {sl} | "
        f"{park_s} | {util_s} | layer={layer} | playbook {PLAYBOOK}"
    )


def format_brief_lines(status: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """Console block + JSON fragment for daily/weekly briefs."""
    st = status or build_trend_repair_status()
    lines = [
        st.get("operator_summary") or "TREND-REPAIR: n/a",
        f"  diagnosis: {st.get('diagnosis', {}).get('detail', '')}",
    ]
    for r in (st.get("recommendations") or [])[:4]:
        lines.append(f"  T{r.get('tier')}: {r.get('action')} — {r.get('detail', '')[:140]}")
    frag = {
        "trend_repair": {
            "as_of": st.get("as_of"),
            "health": (st.get("equity_trend") or {}).get("health"),
            "window_return_pct": (st.get("equity_trend") or {}).get("window_return_pct"),
            "recent_return_pct": (st.get("equity_trend") or {}).get("recent_return_pct"),
            "slope_pct_per_day": ((st.get("equity_trend") or {}).get("trend") or {}).get("slope_pct_per_day"),
            "primary_layer": (st.get("diagnosis") or {}).get("primary_layer"),
            "recommendations": st.get("recommendations"),
            "playbook": PLAYBOOK,
        }
    }
    return "\n".join(lines), frag


def persist_status(status: Optional[Dict[str, Any]] = None, path: Path = STATUS_PATH) -> Path:
    st = status or build_trend_repair_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, indent=2, default=str) + "\n")
    return path


def main() -> int:
    st = build_trend_repair_status()
    p = persist_status(st)
    text, _ = format_brief_lines(st)
    print(text)
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
