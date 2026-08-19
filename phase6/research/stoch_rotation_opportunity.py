"""
Offline: allocator/rotation missed-opportunity view using Stoch shadow logs.

Real data only. No live config. Rebuilds shadow for pre-instrumentation rows
from indicator_snapshot when rotation_shadow is missing.

Forward returns: chained decision price_snapshot (when present) + trade fills.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.rotation_shadow import build_rotation_shadow

DECISION_LOG = STATE_DIR / "decision_context_log.jsonl"
TRADES = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
REPORTS = PROJECT_ROOT / "reports"


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            o = json.loads(line)
            if isinstance(o, dict):
                out.append(o)
        except Exception:
            continue
    return out


def _ensure_shadow(row: Dict[str, Any]) -> Dict[str, Any]:
    shadow = row.get("rotation_shadow")
    if isinstance(shadow, dict) and shadow.get("schema_version"):
        return shadow
    snap = row.get("indicator_snapshot") or {}
    holdings = row.get("holdings_before") or (shadow or {}).get("holdings_usd") if isinstance(shadow, dict) else None
    # tilted_plan is post-target USD — weak holdings proxy only if nothing else
    if not holdings:
        tp = row.get("tilted_plan")
        if isinstance(tp, dict):
            holdings = {k: float(v) for k, v in tp.items() if v is not None}
    return build_rotation_shadow(
        indicator_snapshot=snap if isinstance(snap, dict) else {},
        actions_taken=row.get("actions_taken") or [],
        holdings_before=holdings if isinstance(holdings, dict) else {},
        cash_usd=row.get("cash_usd"),
    )


def _fwd_return_from_prices(
    pair: str,
    t0: datetime,
    decisions: List[Dict[str, Any]],
    horizons_h: Tuple[int, ...] = (24, 72, 168),
) -> Dict[str, Optional[float]]:
    """Use later decision price_snapshots as discrete marks."""
    out: Dict[str, Optional[float]] = {f"ret_{h}h": None for h in horizons_h}
    p0: Optional[float] = None
    t_base: Optional[datetime] = None
    for d in decisions:
        ts = _parse_ts(d.get("timestamp"))
        if not ts or ts < t0:
            continue
        px = (d.get("price_snapshot") or {}).get(pair)
        if px is None:
            continue
        if p0 is None and (ts - t0).total_seconds() < 3600:
            p0 = float(px)
            t_base = ts
            break
    # looser: first snapshot at or after t0
    if p0 is None:
        for d in decisions:
            ts = _parse_ts(d.get("timestamp"))
            if not ts or ts < t0:
                continue
            px = (d.get("price_snapshot") or {}).get(pair)
            if px is not None:
                p0 = float(px)
                t_base = ts
                break
    if p0 is None or p0 <= 0 or t_base is None:
        return out

    for h in horizons_h:
        target = t_base.timestamp() + h * 3600
        best = None
        best_dt = 1e18
        for d in decisions:
            ts = _parse_ts(d.get("timestamp"))
            if not ts:
                continue
            px = (d.get("price_snapshot") or {}).get(pair)
            if px is None:
                continue
            dt = abs(ts.timestamp() - target)
            if ts.timestamp() >= t_base.timestamp() and dt < best_dt:
                best_dt = dt
                best = float(px)
        # require within 75% of horizon window
        if best is not None and best_dt <= h * 3600 * 0.75 and p0 > 0:
            out[f"ret_{h}h"] = round((best / p0) - 1.0, 6)
    return out


def _trade_entry_price(trades: List[Dict[str, Any]], pair: str, around: datetime, window_h: float = 6.0) -> Optional[float]:
    best = None
    best_dt = 1e18
    for t in trades:
        if str(t.get("pair") or "") != pair:
            continue
        side = str(t.get("side") or "").upper()
        if side not in ("BUY", "B"):
            continue
        ts = _parse_ts(t.get("timestamp"))
        if not ts:
            continue
        dt = abs((ts - around).total_seconds())
        if dt <= window_h * 3600 and dt < best_dt:
            px = t.get("entry_price") or t.get("price")
            try:
                if px is not None:
                    best = float(px)
                    best_dt = dt
            except (TypeError, ValueError):
                pass
    return best


def run_analysis(
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, Any]:
    decisions = _load_jsonl(DECISION_LOG)
    trades = _load_jsonl(TRADES)
    end = end or datetime.now(timezone.utc)
    rows = []
    for d in decisions:
        ts = _parse_ts(d.get("timestamp"))
        if not ts:
            continue
        if start and ts < start:
            continue
        if ts > end:
            continue
        # focus rebalance paths
        path = str(d.get("rebalance_path") or "")
        if path.startswith("backfill"):
            continue
        rows.append(d)

    flag_counts: Counter = Counter()
    missed_buy_events = 0
    missed_sell_events = 0
    disagree_events = 0
    decisions_with_shadow_native = 0
    decisions_with_buys = 0
    episodes: List[Dict[str, Any]] = []
    buy_vs_alt: List[Dict[str, Any]] = []

    for d in rows:
        shadow = _ensure_shadow(d)
        if d.get("rotation_shadow"):
            decisions_with_shadow_native += 1
        summary = shadow.get("summary") or {}
        for f in shadow.get("action_flags") or []:
            flag_counts[f.get("flag") or "?"] += 1
        mb = shadow.get("missed_stoch_buys") or []
        ms = shadow.get("missed_stoch_sells") or []
        missed_buy_events += len(mb)
        missed_sell_events += len(ms)
        disagree_events += len(shadow.get("rsi_stoch_disagreements") or [])
        buys = shadow.get("buys") or {}
        if buys:
            decisions_with_buys += 1
        ts = _parse_ts(d.get("timestamp"))
        if not ts:
            continue
        # episode when capital moved and Stoch disagreed with chosen buys
        if buys and (mb or any(f.get("flag") == "buy_stoch_overbought" for f in shadow.get("action_flags") or [])):
            ep = {
                "decision_id": d.get("decision_id"),
                "timestamp": d.get("timestamp"),
                "path": d.get("rebalance_path"),
                "strategy": d.get("strategy_used"),
                "buys": buys,
                "missed_stoch_buys": mb[:5],
                "action_flags": shadow.get("action_flags") or [],
                "buy_rank_compare": shadow.get("buy_rank_compare") or [],
            }
            # forward returns bought vs first missed alt
            bought_rets = {}
            for pair in list(buys.keys())[:4]:
                bought_rets[pair] = _fwd_return_from_prices(pair, ts, rows)
            alt_rets = {}
            for m in mb[:3]:
                pair = m.get("pair")
                if pair:
                    alt_rets[pair] = _fwd_return_from_prices(str(pair), ts, rows)
            ep["fwd_bought"] = bought_rets
            ep["fwd_missed_stoch_alts"] = alt_rets
            # simple 72h compare when both available
            b72 = [v.get("ret_72h") for v in bought_rets.values() if v.get("ret_72h") is not None]
            a72 = [v.get("ret_72h") for v in alt_rets.values() if v.get("ret_72h") is not None]
            if b72 and a72:
                mean_b = sum(b72) / len(b72)
                mean_a = sum(a72) / len(a72)
                ep["compare_72h"] = {
                    "mean_bought": round(mean_b, 6),
                    "mean_stoch_alt": round(mean_a, 6),
                    "delta_alt_minus_bought": round(mean_a - mean_b, 6),
                    "stoch_alt_better": mean_a > mean_b,
                }
                buy_vs_alt.append(ep["compare_72h"])
            episodes.append(ep)

    # Aggregate alt edge
    alt_better = sum(1 for c in buy_vs_alt if c.get("stoch_alt_better"))
    n_cmp = len(buy_vs_alt)
    mean_delta = (
        round(sum(c["delta_alt_minus_bought"] for c in buy_vs_alt) / n_cmp, 6) if n_cmp else None
    )

    # Recommendation (observe-only language)
    native_ratio = decisions_with_shadow_native / max(1, len(rows))
    if n_cmp < 5:
        enum = "extend_collect"
        plain = (
            "Not enough forward-priced missed-buy comparisons yet. "
            "Keep logging rotation_shadow + price_snapshot on each rebalance."
        )
    elif mean_delta is not None and mean_delta > 0.01 and alt_better / n_cmp >= 0.6:
        enum = "weak_missed_opp_observe"
        plain = (
            "Stoch-preferred alts beat chosen buys on mean 72h in a majority of tagged episodes — "
            "still observe-only; do not change allocator."
        )
    elif mean_delta is not None and mean_delta < -0.01:
        enum = "no_rotation_edge"
        plain = "Chosen buys beat Stoch alts on average — no missed-opportunity case for Stoch rotation overlay."
    else:
        enum = "no_clear_edge"
        plain = "No clear Stoch missed-opportunity edge on allocator/rotation decisions yet."

    return {
        "window": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat(),
            "n_decisions": len(rows),
            "n_with_native_shadow": decisions_with_shadow_native,
            "native_shadow_ratio": round(native_ratio, 3),
            "n_with_buys": decisions_with_buys,
        },
        "flag_counts": dict(flag_counts),
        "missed_stoch_buy_events": missed_buy_events,
        "missed_stoch_sell_events": missed_sell_events,
        "disagreement_pair_events": disagree_events,
        "forward_compare_72h": {
            "n": n_cmp,
            "stoch_alt_better_n": alt_better,
            "mean_delta_alt_minus_bought": mean_delta,
        },
        "episodes": episodes[-40:],  # cap
        "recommendation": {
            "enum": enum,
            "plain_english": plain,
            "go_allocator_change": False,
            "go_live_rotation_overlay": False,
            "live_allocator_unchanged": True,
        },
        "notes": [
            "Shadow is log-only; live path stays plain RSI allocator.",
            "Pre-shadow rows rebuild candidates from indicator_snapshot; holdings may be tilted_plan proxy.",
            "Forward returns need price_snapshot on decisions — sparse until this deploy ages.",
            "Trade fill prices available as secondary marks; not used as primary basket marks yet.",
        ],
        "trades_loaded": len(trades),
    }


def render_markdown(analysis: Dict[str, Any], title_id: str = "STOCH-ROTATION-OPP") -> str:
    rec = analysis.get("recommendation") or {}
    w = analysis.get("window") or {}
    fc = analysis.get("flag_counts") or {}
    fwd = analysis.get("forward_compare_72h") or {}
    lines = [
        f"# Stoch rotation / allocator opportunity — offline",
        "",
        f"**ID:** `{title_id}`  ",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ",
        f"**Recommendation:** **{rec.get('enum')}**  ",
        f"**Plain English:** {rec.get('plain_english')}  ",
        "",
        "## Window",
        "",
        f"- Decisions: **{w.get('n_decisions')}** | native rotation_shadow: **{w.get('n_with_native_shadow')}** "
        f"({w.get('native_shadow_ratio')}) | with buys: **{w.get('n_with_buys')}**",
        f"- Range: `{w.get('start')}` → `{w.get('end')}`",
        "",
        "## Decision-time flags (counts)",
        "",
    ]
    if fc:
        for k, v in sorted(fc.items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{k}`: **{v}**")
    else:
        lines.append("- (none)")
    lines += [
        "",
        "## Missed Stoch candidates (event counts)",
        "",
        f"- missed_stoch_buys: **{analysis.get('missed_stoch_buy_events')}**",
        f"- missed_stoch_sells: **{analysis.get('missed_stoch_sell_events')}**",
        f"- RSI mid vs Stoch extreme pair-events: **{analysis.get('disagreement_pair_events')}**",
        "",
        "## Forward 72h: bought vs Stoch alt (when both priced)",
        "",
        f"- n comparisons: **{fwd.get('n')}**",
        f"- stoch alt better: **{fwd.get('stoch_alt_better_n')}**",
        f"- mean Δ (alt − bought): **{fwd.get('mean_delta_alt_minus_bought')}**",
        "",
        "## Gates",
        "",
        f"- Allocator change: **{rec.get('go_allocator_change')}**",
        f"- Live rotation overlay: **{rec.get('go_live_rotation_overlay')}**",
        "",
        "## Notes",
        "",
    ]
    for n in analysis.get("notes") or []:
        lines.append(f"- {n}")
    eps = analysis.get("episodes") or []
    if eps:
        lines += ["", "## Recent tagged episodes (tail)", ""]
        for ep in eps[-8:]:
            lines.append(
                f"- `{ep.get('timestamp')}` buys={list((ep.get('buys') or {}).keys())} "
                f"missed={[m.get('pair') for m in (ep.get('missed_stoch_buys') or [])]} "
                f"cmp={ep.get('compare_72h')}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Stoch rotation missed-opportunity offline dig")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--phase", default="offline")
    args = ap.parse_args()
    start = _parse_ts(args.start) if args.start else _parse_ts("2026-07-21T00:00:00+00:00")
    end = _parse_ts(args.end) if args.end else datetime.now(timezone.utc)
    analysis = run_analysis(start=start, end=end)
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"STOCH_ROTATION_OPP_{args.phase.upper()}_{day}"
    md = REPORTS / f"{stem}.md"
    js = REPORTS / f"{stem}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "analysis": analysis,
        "rules": {
            "allocator_change": False,
            "live_rotation_overlay": False,
            "real_data_only": True,
        },
    }
    js.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    md.write_text(render_markdown(analysis))
    print(md)
    print(js)
    print("enum", (analysis.get("recommendation") or {}).get("enum"))
    print("plain", (analysis.get("recommendation") or {}).get("plain_english"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
