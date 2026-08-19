"""
Log-only rotation / allocator shadow for Stoch vs plain RSI.

Does NOT change live allocator, scores, or orders.
Attaches structured fields so offline analysis can ask:
  - Did we buy overbought Stoch / sell oversold Stoch?
  - Which basket names would Stoch have preferred instead?
  - RSI↔Stoch rank disagreements at decision time?
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

SHADOW_SCHEMA_VERSION = 1

# Fixed trial thresholds (no in-loop search)
STOCH_OVERSOLD = 30.0
STOCH_VERY_OVERSOLD = 20.0
STOCH_OVERBOUGHT = 80.0
RSI_OVERSOLD = 35.0
RSI_OVERBOUGHT = 70.0
RSI_NEUTRAL = (40.0, 60.0)
TOP_N = 3


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _rank_pairs(
    indicator_snapshot: Dict[str, Any],
    key: str,
    *,
    ascending: bool = True,
) -> List[Dict[str, Any]]:
    rows: List[Tuple[str, float]] = []
    for pair, rec in (indicator_snapshot or {}).items():
        if not isinstance(rec, dict):
            continue
        v = _f(rec.get(key))
        if v is None:
            continue
        rows.append((str(pair), v))
    rows.sort(key=lambda t: t[1], reverse=not ascending)
    out: List[Dict[str, Any]] = []
    for i, (pair, val) in enumerate(rows, start=1):
        out.append({"pair": pair, key: round(val, 4), "rank": i})
    return out


def _action_sets(actions: Sequence[Any]) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    buys: Dict[str, float] = {}
    sells: Dict[str, float] = {}
    reasons: List[str] = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        pair = str(a.get("pair") or a.get("product_id") or "")
        if not pair:
            continue
        side = str(a.get("action") or a.get("side") or "").upper()
        usd = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount")) or 0.0
        reason = str(a.get("reason") or "")
        if reason:
            reasons.append(f"{pair}:{side}:{reason}")
        if side in ("BUY", "B"):
            buys[pair] = buys.get(pair, 0.0) + usd
        elif side in ("SELL", "S"):
            sells[pair] = sells.get(pair, 0.0) + usd
    return buys, sells, reasons


def _holdings_usd(holdings: Optional[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not holdings:
        return out
    raw = holdings
    if isinstance(holdings, dict) and "positions" in holdings and isinstance(holdings["positions"], dict):
        raw = holdings.get("value_usd") or holdings["positions"]
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        pair = str(k)
        if isinstance(v, dict):
            usd = _f(v.get("value_usd") if v.get("value_usd") is not None else v.get("amount"))
        else:
            usd = _f(v)
        if usd is None:
            continue
        out[pair] = float(usd)
    return out


def build_rotation_shadow(
    *,
    indicator_snapshot: Optional[Dict[str, Any]],
    actions_taken: Optional[Sequence[Any]] = None,
    holdings_before: Optional[Dict[str, Any]] = None,
    cash_usd: Optional[float] = None,
    top_n: int = TOP_N,
    stoch_os: float = STOCH_OVERSOLD,
    stoch_ob: float = STOCH_OVERBOUGHT,
) -> Dict[str, Any]:
    """
    Pure function: shadow view of one rebalance decision.

    Returns JSON-serializable dict for decision_context_log.
    """
    snap = indicator_snapshot or {}
    buys, sells, reason_tags = _action_sets(actions_taken or [])
    hold = _holdings_usd(holdings_before)

    rsi_rank = _rank_pairs(snap, "rsi", ascending=True)  # low RSI first (oversold)
    stoch_rank = _rank_pairs(snap, "stoch_k", ascending=True)

    def _top(ranks: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        return ranks[: max(0, int(n))]

    # Disagreements: RSI mid-band but Stoch extreme (same class as trial report)
    disagreements: List[Dict[str, Any]] = []
    for pair, rec in snap.items():
        if not isinstance(rec, dict):
            continue
        rsi = _f(rec.get("rsi"))
        sk = _f(rec.get("stoch_k"))
        if rsi is None or sk is None:
            continue
        lo, hi = RSI_NEUTRAL
        if lo <= rsi <= hi and (sk < STOCH_VERY_OVERSOLD or sk > stoch_ob):
            disagreements.append(
                {
                    "pair": pair,
                    "rsi": rsi,
                    "stoch_k": sk,
                    "kind": "stoch_os_rsi_mid" if sk < STOCH_VERY_OVERSOLD else "stoch_ob_rsi_mid",
                }
            )

    # Stoch preferred buy candidates: lowest stoch_k among oversold, not already maxed narrative
    stoch_buy_cands = [
        r
        for r in stoch_rank
        if r.get("stoch_k") is not None and float(r["stoch_k"]) < stoch_os
    ][:top_n]
    rsi_buy_cands = [
        r for r in rsi_rank if r.get("rsi") is not None and float(r["rsi"]) < RSI_OVERSOLD
    ][:top_n]

    stoch_sell_cands = [
        r
        for r in _rank_pairs(snap, "stoch_k", ascending=False)
        if r.get("stoch_k") is not None and float(r["stoch_k"]) > stoch_ob
    ][:top_n]
    rsi_sell_cands = [
        r
        for r in _rank_pairs(snap, "rsi", ascending=False)
        if r.get("rsi") is not None and float(r["rsi"]) > RSI_OVERBOUGHT
    ][:top_n]

    bought_pairs = set(buys)
    sold_pairs = set(sells)

    # Missed buys: Stoch oversold top-N not bought while any BUY happened (capital was moving)
    missed_stoch_buys = []
    if bought_pairs:
        for r in stoch_buy_cands:
            if r["pair"] not in bought_pairs:
                missed_stoch_buys.append(
                    {
                        **r,
                        "note": "stoch_oversold_not_bought_while_buys_occurred",
                        "holding_usd": round(hold.get(r["pair"], 0.0), 4),
                    }
                )

    # Missed sells: Stoch overbought held and not sold while rotation sells occurred
    missed_stoch_sells = []
    if sold_pairs:
        for r in stoch_sell_cands:
            p = r["pair"]
            if p not in sold_pairs and hold.get(p, 0.0) > 1.0:
                missed_stoch_sells.append(
                    {
                        **r,
                        "note": "stoch_overbought_held_while_sells_occurred",
                        "holding_usd": round(hold.get(p, 0.0), 4),
                    }
                )

    # Action quality flags (narrative — not live gates)
    flags: List[Dict[str, Any]] = []
    for pair, usd in buys.items():
        rec_raw = snap.get(pair)
        rec = rec_raw if isinstance(rec_raw, dict) else {}
        sk = _f(rec.get("stoch_k"))
        rsi = _f(rec.get("rsi"))
        if sk is not None and sk > stoch_ob:
            flags.append(
                {
                    "pair": pair,
                    "side": "BUY",
                    "usd": round(usd, 4),
                    "flag": "buy_stoch_overbought",
                    "stoch_k": sk,
                    "rsi": rsi,
                }
            )
        if sk is not None and sk < stoch_os:
            flags.append(
                {
                    "pair": pair,
                    "side": "BUY",
                    "usd": round(usd, 4),
                    "flag": "buy_stoch_oversold",
                    "stoch_k": sk,
                    "rsi": rsi,
                }
            )
    for pair, usd in sells.items():
        rec_raw = snap.get(pair)
        rec = rec_raw if isinstance(rec_raw, dict) else {}
        sk = _f(rec.get("stoch_k"))
        rsi = _f(rec.get("rsi"))
        if sk is not None and sk < stoch_os:
            flags.append(
                {
                    "pair": pair,
                    "side": "SELL",
                    "usd": round(usd, 4),
                    "flag": "sell_stoch_oversold",
                    "stoch_k": sk,
                    "rsi": rsi,
                }
            )
        if sk is not None and sk > stoch_ob:
            flags.append(
                {
                    "pair": pair,
                    "side": "SELL",
                    "usd": round(usd, 4),
                    "flag": "sell_stoch_overbought",
                    "stoch_k": sk,
                    "rsi": rsi,
                }
            )

    # Rank of each buy under RSI vs Stoch (1 = most oversold)
    rsi_rank_map = {r["pair"]: r["rank"] for r in rsi_rank}
    stoch_rank_map = {r["pair"]: r["rank"] for r in stoch_rank}
    buy_rank_compare = []
    for pair, usd in buys.items():
        buy_rank_compare.append(
            {
                "pair": pair,
                "usd": round(usd, 4),
                "rsi_oversold_rank": rsi_rank_map.get(pair),
                "stoch_oversold_rank": stoch_rank_map.get(pair),
                "rsi": _f((snap.get(pair) or {}).get("rsi")) if isinstance(snap.get(pair), dict) else None,
                "stoch_k": _f((snap.get(pair) or {}).get("stoch_k"))
                if isinstance(snap.get(pair), dict)
                else None,
            }
        )

    n_basket = len(snap)
    rank_delta_sum = 0
    rank_delta_n = 0
    for pair in bought_pairs:
        a, b = rsi_rank_map.get(pair), stoch_rank_map.get(pair)
        if a is not None and b is not None:
            rank_delta_sum += abs(a - b)
            rank_delta_n += 1

    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "live_allocator_unchanged": True,
        "thresholds": {
            "stoch_oversold": stoch_os,
            "stoch_very_oversold": STOCH_VERY_OVERSOLD,
            "stoch_overbought": stoch_ob,
            "rsi_oversold": RSI_OVERSOLD,
            "rsi_overbought": RSI_OVERBOUGHT,
            "rsi_neutral": list(RSI_NEUTRAL),
            "top_n": top_n,
        },
        "cash_usd": round(float(cash_usd), 4) if cash_usd is not None else None,
        "holdings_usd": {k: round(v, 4) for k, v in sorted(hold.items()) if v > 0.01},
        "buys": {k: round(v, 4) for k, v in buys.items()},
        "sells": {k: round(v, 4) for k, v in sells.items()},
        "rsi_oversold_rank": _top(rsi_rank, top_n),
        "stoch_oversold_rank": _top(stoch_rank, top_n),
        "rsi_overbought_rank": rsi_sell_cands,
        "stoch_overbought_rank": stoch_sell_cands,
        "stoch_buy_candidates": stoch_buy_cands,
        "rsi_buy_candidates": rsi_buy_cands,
        "missed_stoch_buys": missed_stoch_buys,
        "missed_stoch_sells": missed_stoch_sells,
        "rsi_stoch_disagreements": disagreements,
        "action_flags": flags,
        "buy_rank_compare": buy_rank_compare,
        "summary": {
            "basket_pairs": n_basket,
            "n_buys": len(buys),
            "n_sells": len(sells),
            "n_missed_stoch_buys": len(missed_stoch_buys),
            "n_missed_stoch_sells": len(missed_stoch_sells),
            "n_disagreements": len(disagreements),
            "n_action_flags": len(flags),
            "mean_abs_buy_rank_delta_rsi_vs_stoch": (
                round(rank_delta_sum / rank_delta_n, 3) if rank_delta_n else None
            ),
            "reason_tags_sample": reason_tags[:12],
        },
    }


def extract_holdings_and_cash(runner: Any) -> Tuple[Dict[str, float], Optional[float]]:
    """Best-effort holdings USD + cash from runner (never raises)."""
    holdings: Dict[str, float] = {}
    cash: Optional[float] = None
    try:
        portfolio = getattr(runner, "portfolio", None)
        if portfolio is not None:
            enr = portfolio.get_enriched_positions() or {}
            holdings = _holdings_usd(enr if isinstance(enr, dict) else {})
    except Exception:
        pass
    try:
        ex = getattr(runner, "exchange", None)
        if ex is not None and hasattr(ex, "get_account_balance"):
            cash = _f(ex.get_account_balance("USD"))
            usdc = _f(ex.get_account_balance("USDC"))
            if cash is not None or usdc is not None:
                cash = (cash or 0.0) + (usdc or 0.0)
    except Exception:
        pass
    # Fallback: last plan allocations if holdings empty
    if not holdings:
        try:
            plan = getattr(runner, "_last_plan", None)
            na = getattr(plan, "new_allocations", None) if plan is not None else None
            if isinstance(na, dict):
                holdings = {str(k): float(v) for k, v in na.items() if _f(v) is not None}
        except Exception:
            pass
    return holdings, cash


def load_price_snapshot(universe: Optional[Sequence[str]] = None) -> Dict[str, float]:
    """Last close from price_history.json (real series used by RSI refresher)."""
    from phase6.core.paths import PROJECT_ROOT

    path = PROJECT_ROOT / "data" / "state" / "price_history.json"
    out: Dict[str, float] = {}
    try:
        root = json_loads_safe(path)
        hist = (root or {}).get("history") or {}
        if not isinstance(hist, dict):
            return out
        pairs = list(universe) if universe else list(hist.keys())
        for pair in pairs:
            series = hist.get(pair) or []
            if isinstance(series, list) and series:
                px = _f(series[-1])
                if px is not None and px > 0:
                    out[str(pair)] = round(px, 8)
    except Exception:
        return out
    return out


def json_loads_safe(path: Any) -> Dict[str, Any]:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}
