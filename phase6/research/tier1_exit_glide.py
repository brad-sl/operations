"""Tier 1 exit scan + draft util glide (no execution).

Uses REGIME-CASH prefer_exit knobs + park util target. Writes:
  data/state/tier1_exit_glide_draft.json

See docs/TREND_REPAIR_PLAYBOOK.md §4 Tier 1.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = ROOT / "data" / "state" / "tier1_exit_glide_draft.json"
LIVE_STATE = ROOT / "data" / "state" / "phase6_live_state.json"
RSI_CACHE = ROOT / "data" / "state" / "rsi_cache.json"
SENT_CACHE = ROOT / "data" / "state" / "sentiment_cache.json"
REGIME_STATUS = ROOT / "data" / "state" / "regime_cash_status.json"

# Draft safety (proposal only — never auto-execute)
MAX_GLIDE_USD = 400.0  # total notional to propose this pass
MAX_PAIR_FRACTION = 0.35  # max fraction of a position per draft leg
MIN_LEG_USD = 25.0
MIN_REMAIN_USD = 15.0  # leave dust rather than full exit unless hard exit
HARD_EXIT_FULL = True  # hard knob hits may propose full position (still draft only)


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _rsi_map() -> Dict[str, float]:
    raw = _load(RSI_CACHE)
    data = raw.get("rsi") or raw.get("data") or raw
    out: Dict[str, float] = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if isinstance(v, dict):
            r = v.get("rsi")
            if r is not None:
                try:
                    out[str(k)] = float(r)
                except (TypeError, ValueError):
                    pass
        else:
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def _sent_map() -> Dict[str, float]:
    raw = _load(SENT_CACHE)
    data = raw.get("scores") or raw.get("data") or raw.get("sentiment") or raw
    out: Dict[str, float] = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        if isinstance(v, dict):
            s = v.get("score", v.get("sentiment", v.get("value")))
        else:
            s = v
        try:
            if s is None:
                continue
            out[str(k)] = float(s)
        except (TypeError, ValueError):
            pass
    return out


def _positions(live: Dict[str, Any]) -> List[Dict[str, Any]]:
    positions = live.get("trading_positions") or live.get("positions") or []
    try:
        from phase6.core.position_cost_basis import recompute_trading_positions_pnl

        positions = recompute_trading_positions_pnl(list(positions))
    except Exception:
        pass
    rows = []
    for p in positions:
        pair = str(p.get("pair") or "")
        if pair in ("USD", "USDC", ""):
            continue
        val = float(p.get("value_usd") or 0.0)
        if val < 1.0:
            continue
        upct = p.get("unrealized_pnl_pct")
        try:
            up = float(upct) if upct is not None else 0.0
        except (TypeError, ValueError):
            up = 0.0
        if abs(up) <= 2.0 and up != 0.0:
            up *= 100.0
        try:
            uusd = float(p.get("unrealized_pnl_usd") or 0.0)
        except (TypeError, ValueError):
            uusd = val * up / 100.0
        qty = float(p.get("qty") or p.get("quantity") or 0.0)
        rows.append(
            {
                "pair": pair,
                "value_usd": round(val, 2),
                "unrealized_pnl_pct": round(up, 2),
                "unrealized_pnl_usd": round(uusd, 2),
                "qty": qty,
                "entry_price": p.get("entry_price") or p.get("avg_entry"),
            }
        )
    return rows


def _classify_exit(reasons: List[str]) -> str:
    hard = [r for r in reasons if r.startswith("rsi_overbought") or r.startswith("sentiment_weak")]
    if hard:
        return "hard_exit"
    if any(r == "park_prefer_reduce" for r in reasons):
        return "park_soft"
    return "hold"


def scan_and_draft_glide(
    *,
    max_glide_usd: float = MAX_GLIDE_USD,
    max_pair_fraction: float = MAX_PAIR_FRACTION,
    target_util_override: Optional[float] = None,
) -> Dict[str, Any]:
    from phase6.core.regime_cash_policy import prefer_exit, resolve_regime_cash

    live = _load(LIVE_STATE)
    rsi_m = _rsi_map()
    sent_m = _sent_map()
    snap = resolve_regime_cash()
    target_util = (
        float(target_util_override)
        if target_util_override is not None
        else float(snap.target_max_util_pct or 0.45)
    )

    total = float(live.get("total_usd") or live.get("total_balance") or 0.0)
    holdings = live.get("total_holdings_value")
    if holdings is None:
        cash = float(live.get("cash_usd") or live.get("cash_balance") or 0.0)
        holdings = max(0.0, total - cash)
    else:
        holdings = float(holdings)
        cash = float(live.get("cash_usd") or live.get("cash_balance") or max(0.0, total - holdings))
    util = (holdings / total) if total > 0 else 0.0
    target_holdings = target_util * total
    reduce_needed = max(0.0, holdings - target_holdings)

    pos = _positions(live)
    scans: List[Dict[str, Any]] = []
    for p in pos:
        pair = p["pair"]
        dec = prefer_exit(pair, snap, sentiment=sent_m.get(pair), rsi=rsi_m.get(pair))
        reasons = list(dec.reasons or [])
        cls = _classify_exit(reasons)
        scans.append(
            {
                **p,
                "rsi": rsi_m.get(pair),
                "sentiment": sent_m.get(pair),
                "exit_class": cls,
                "exit_reasons": reasons,
                "prefer_exit": bool(dec.allowed),
            }
        )

    # Rank: hard_exit first, then park_soft underwater before winners, larger drag first
    def sort_key(r: Dict[str, Any]) -> Tuple[int, int, float, float]:
        cls_rank = 0 if r["exit_class"] == "hard_exit" else (1 if r["exit_class"] == "park_soft" else 9)
        # 0 = red/flat MTM first, 1 = green (only if budget remains)
        green = 1 if (r.get("unrealized_pnl_usd") or 0) > 5 else 0
        return (cls_rank, green, r.get("unrealized_pnl_usd") or 0.0, -(r.get("value_usd") or 0.0))

    ranked = sorted([r for r in scans if r["exit_class"] != "hold"], key=sort_key)

    glide_legs: List[Dict[str, Any]] = []
    remaining_budget = min(max_glide_usd, reduce_needed if reduce_needed > 0 else max_glide_usd * 0.25)
    # If already under target, only propose hard exits (small)
    only_hard = reduce_needed <= 1.0

    for r in ranked:
        if remaining_budget < MIN_LEG_USD:
            break
        if only_hard and r["exit_class"] != "hard_exit":
            continue
        # Prefer not cutting winners until reds exhausted; skip green park_soft if reds still available
        if r["exit_class"] == "park_soft" and (r.get("unrealized_pnl_usd") or 0) > 5:
            reds_left = any(
                x["exit_class"] == "park_soft"
                and (x.get("unrealized_pnl_usd") or 0) <= 5
                and x["pair"] not in {l["pair"] for l in glide_legs}
                for x in ranked
            )
            # If still need a lot of util and only greens left, allow small winner trim later
            if reds_left:
                continue
            # Cap winner trims tighter
            max_pair_fraction_eff = min(max_pair_fraction, 0.15)
        else:
            max_pair_fraction_eff = max_pair_fraction
        val = float(r["value_usd"])
        if r["exit_class"] == "hard_exit" and HARD_EXIT_FULL:
            sell_usd = min(val, remaining_budget)
        else:
            # park soft: fraction of book, prefer underwater names get larger share
            frac = max_pair_fraction_eff
            if (r.get("unrealized_pnl_pct") or 0) < -3:
                frac = min(0.5, max_pair_fraction_eff + 0.1)
            sell_usd = min(val * frac, remaining_budget)
            if val - sell_usd < MIN_REMAIN_USD and val > MIN_REMAIN_USD:
                sell_usd = max(0.0, val - MIN_REMAIN_USD)
        if sell_usd < MIN_LEG_USD:
            continue
        sell_usd = round(sell_usd, 2)
        qty_frac = sell_usd / val if val > 0 else 0.0
        qty_sell = round(float(r.get("qty") or 0.0) * qty_frac, 8) if r.get("qty") else None
        glide_legs.append(
            {
                "pair": r["pair"],
                "side": "SELL",
                "exit_class": r["exit_class"],
                "reasons": r["exit_reasons"],
                "position_usd": val,
                "sell_usd": sell_usd,
                "qty_sell_est": qty_sell,
                "unrealized_pnl_pct": r.get("unrealized_pnl_pct"),
                "rsi": r.get("rsi"),
                "sentiment": r.get("sentiment"),
                "execute": False,
            }
        )
        remaining_budget -= sell_usd

    proposed_reduce = round(sum(l["sell_usd"] for l in glide_legs), 2)
    util_after = ((holdings - proposed_reduce) / total) if total > 0 else util

    draft = {
        "schema": "tier1_exit_glide_draft_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "execute": False,
        "auto_apply": False,
        "playbook": "docs/TREND_REPAIR_PLAYBOOK.md",
        "regime": {
            "regime": snap.regime,
            "strategy_mode": snap.strategy_mode,
            "allow_new_buys": snap.allow_new_buys,
            "target_max_util_pct": snap.target_max_util_pct,
            "exit_knobs": snap.exit,
            "enforce": snap.enforce,
        },
        "capital": {
            "total_usd": round(total, 2),
            "cash_usd": round(cash, 2),
            "holdings_usd": round(holdings, 2),
            "util": round(util, 4),
            "target_util": target_util,
            "reduce_needed_usd": round(reduce_needed, 2),
            "util_after_if_filled": round(util_after, 4),
        },
        "scan": scans,
        "glide_legs": glide_legs,
        "proposed_reduce_usd": proposed_reduce,
        "limits": {
            "max_glide_usd": max_glide_usd,
            "max_pair_fraction": max_pair_fraction,
            "min_leg_usd": MIN_LEG_USD,
        },
        "operator_next": (
            "DRAFT ONLY — no orders placed. Review glide_legs; approve a subset or "
            "`PYTHONPATH=. .venv/bin/python3 -m phase6.research.tier1_exit_glide --execute` "
            "is intentionally NOT implemented. Execute via runner/manual with explicit Brad OK."
        ),
        "notes": [
            "prefer_exit under usdc_park tags all holds with park_prefer_reduce (soft).",
            "hard_exit = RSI overbought or sentiment <= max_sentiment_hold only.",
            "Park soft glide prioritizes worse MTM; does not invent edge.",
            "BUYs remain blocked while park; this draft is SELL-only.",
        ],
    }
    return draft


def persist(draft: Dict[str, Any], path: Path = OUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, indent=2, default=str) + "\n")
    return path


def format_summary(draft: Dict[str, Any]) -> str:
    c = draft.get("capital") or {}
    lines = [
        f"TIER1 exit scan DRAFT (execute=false) as_of={draft.get('as_of')}",
        f"  util {c.get('util'):.1%} → target {c.get('target_util'):.0%} | "
        f"reduce_needed ${c.get('reduce_needed_usd')} | proposed ${draft.get('proposed_reduce_usd')} "
        f"| util_after~{c.get('util_after_if_filled'):.1%}",
        f"  regime { (draft.get('regime') or {}).get('regime') } "
        f"mode={(draft.get('regime') or {}).get('strategy_mode')}",
    ]
    hard = [s for s in draft.get("scan") or [] if s.get("exit_class") == "hard_exit"]
    soft = [s for s in draft.get("scan") or [] if s.get("exit_class") == "park_soft"]
    lines.append(f"  scan: hard_exit={len(hard)} park_soft={len(soft)} hold={len((draft.get('scan') or []))-len(hard)-len(soft)}")
    if hard:
        lines.append("  HARD exits:")
        for s in hard:
            lines.append(
                f"    {s['pair']}: ${s['value_usd']} pnl={s.get('unrealized_pnl_pct')}% "
                f"rsi={s.get('rsi')} sent={s.get('sentiment')} {s.get('exit_reasons')}"
            )
    lines.append("  Draft glide legs:")
    if not draft.get("glide_legs"):
        lines.append("    (none — no legs met min size / only_hard filter)")
    for leg in draft.get("glide_legs") or []:
        lines.append(
            f"    SELL {leg['pair']} ${leg['sell_usd']} of ${leg['position_usd']} "
            f"[{leg['exit_class']}] pnl={leg.get('unrealized_pnl_pct')}% reasons={leg.get('reasons')}"
        )
    lines.append(f"  {draft.get('operator_next')}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv or sys.argv[1:])
    if "--execute" in argv:
        print("REFUSED: --execute not implemented. Draft only. Explicit operator path required.")
        return 2
    draft = scan_and_draft_glide()
    p = persist(draft)
    print(format_summary(draft))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
