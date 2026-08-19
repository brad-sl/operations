"""
Classify portfolio changes that are NOT external deposits/withdrawals.

Manual sells (OP → USD) and manual crypto swaps must not be mistaken for
deposits or trigger blind auto-rebuy of liquidated names.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MIN_DISPOSITION_USD = 50.0


def normalize_position_values(raw: Any) -> Dict[str, float]:
    if not raw:
        return {}
    if isinstance(raw, dict) and "positions" in raw:
        raw = raw.get("positions") or raw.get("value_usd") or {}
    out: Dict[str, float] = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        pair = str(k)
        if not pair.endswith("-USD") and "-" not in pair:
            pair = f"{pair}-USD"
        if isinstance(v, dict):
            out[pair] = float(v.get("value_usd", v.get("amount", 0.0)) or 0.0)
        else:
            out[pair] = float(v or 0.0)
    return out


def pair_deltas(
    prev: Dict[str, float],
    cur: Dict[str, float],
    min_usd: float = MIN_DISPOSITION_USD,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    keys = set(prev) | set(cur)
    decreased: Dict[str, float] = {}
    increased: Dict[str, float] = {}
    for k in keys:
        d = float(cur.get(k, 0.0)) - float(prev.get(k, 0.0))
        if d <= -min_usd:
            decreased[k] = round(d, 2)
        elif d >= min_usd:
            increased[k] = round(d, 2)
    return decreased, increased


def _nav_flat(d_total: float, reference: float, pct: float = 0.08, floor: float = 75.0) -> bool:
    return abs(d_total) <= max(floor, pct * max(abs(reference), 1.0))


def detect_manual_disposition(
    prev_pos: Dict[str, float],
    cur_pos: Dict[str, float],
    delta_cash: float,
    delta_holdings: float,
    delta_total: float,
    min_usd: float = MIN_DISPOSITION_USD,
) -> Optional[Dict[str, Any]]:
    """
    Returns event dict or None.

    event_type:
      - manual_liquidation_to_cash — sold crypto → USD, NAV ~flat
      - manual_crypto_swap — rotated between pairs, cash ~flat
    """
    decreased, increased = pair_deltas(prev_pos, cur_pos, min_usd=min_usd)
    if not decreased and not increased:
        return None

    sold_usd = sum(-v for v in decreased.values())
    bought_usd = sum(increased.values())

    # Manual sell to cash (withdrawal prep or idle USD)
    if decreased and delta_cash >= min_usd and _nav_flat(delta_total, delta_cash):
        cash_from_sells = sold_usd
        if cash_from_sells >= min_usd and delta_cash >= min_usd * 0.85:
            if not increased or bought_usd < min_usd:
                return {
                    "event_type": "manual_liquidation_to_cash",
                    "pairs_sold": list(decreased.keys()),
                    "pairs_bought": list(increased.keys()),
                    "sold_usd": round(sold_usd, 2),
                    "cash_delta_usd": round(delta_cash, 2),
                    "delta_holdings_usd": round(delta_holdings, 2),
                    "delta_total_usd": round(delta_total, 2),
                    "pair_deltas": {**decreased, **increased},
                }

    # Manual swap between pairs (no meaningful cash / NAV change)
    if (
        decreased
        and increased
        and abs(delta_cash) < min_usd
        and _nav_flat(delta_total, sold_usd)
    ):
        if abs(sold_usd - bought_usd) <= max(75.0, 0.15 * sold_usd):
            return {
                "event_type": "manual_crypto_swap",
                "pairs_sold": list(decreased.keys()),
                "pairs_bought": list(increased.keys()),
                "sold_usd": round(sold_usd, 2),
                "bought_usd": round(bought_usd, 2),
                "delta_total_usd": round(delta_total, 2),
                "pair_deltas": {**decreased, **increased},
            }

    # Partial trim with small cash bump (still treat as liquidation intent if cash dominates)
    if decreased and delta_cash > 0 and sold_usd >= min_usd and _nav_flat(delta_total, sold_usd):
        if delta_cash >= sold_usd * 0.5:
            return {
                "event_type": "manual_liquidation_to_cash",
                "pairs_sold": list(decreased.keys()),
                "pairs_bought": list(increased.keys()),
                "sold_usd": round(sold_usd, 2),
                "cash_delta_usd": round(delta_cash, 2),
                "delta_holdings_usd": round(delta_holdings, 2),
                "delta_total_usd": round(delta_total, 2),
                "pair_deltas": {**decreased, **increased},
                "partial": True,
            }

    return None