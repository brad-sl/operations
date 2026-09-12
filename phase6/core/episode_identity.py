"""
Episode / lot identity (bag_id) — A2 full.

Canonical form: ``{PAIR}:{buy_order_id}`` (pair uppercased, buy id stripped).

Migration:
- Historical ledger/registry rows without bag_id remain valid.
- Consumers treat missing bag_id as "unknown" and fall back to entry-px /
  fresh_buy heuristics already in ratchet + peak sanitize.
- When both sides carry bag_id and they differ → hard reject prior-bag state.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


def normalize_pair(pair: Any) -> str:
    return str(pair or "").strip().upper()


def normalize_order_id(order_id: Any) -> str:
    return str(order_id or "").strip()


def make_bag_id(pair: Any, buy_order_id: Any) -> Optional[str]:
    """Return canonical bag_id or None if inputs are incomplete."""
    p = normalize_pair(pair)
    oid = normalize_order_id(buy_order_id)
    if not p or not oid:
        return None
    return f"{p}:{oid}"


def coerce_bag_id(
    *,
    bag_id: Any = None,
    pair: Any = None,
    buy_order_id: Any = None,
) -> Optional[str]:
    """Prefer explicit bag_id; else build from pair + buy_order_id."""
    raw = str(bag_id or "").strip()
    if raw:
        # Normalize pair prefix when shape is pair:id
        if ":" in raw and pair:
            p = normalize_pair(pair)
            _pref, rest = raw.split(":", 1)
            if p and rest.strip():
                return f"{p}:{rest.strip()}"
        return raw
    return make_bag_id(pair, buy_order_id)


def bag_ids_match(a: Any, b: Any) -> bool:
    """True when both known and equal. False if either missing or mismatch."""
    aa = str(a or "").strip()
    bb = str(b or "").strip()
    if not aa or not bb:
        return False
    return aa == bb


def bag_ids_conflict(a: Any, b: Any) -> bool:
    """True only when both known and different (hard prior-bag reject)."""
    aa = str(a or "").strip()
    bb = str(b or "").strip()
    if not aa or not bb:
        return False
    return aa != bb


def stamp_bag_id_on_trade(trade: Mapping[str, Any]) -> dict:
    """
    Ensure trade dict carries bag_id when derivable.

    BUY: bag_id = pair:order_id (the buy itself is the episode seed).
    SELL: keep existing bag_id / buy_order_id; do not invent from sell order_id.
    """
    out = dict(trade)
    pair = out.get("pair") or out.get("product_id")
    side = str(out.get("side") or "").upper()
    existing = coerce_bag_id(
        bag_id=out.get("bag_id"),
        pair=pair,
        buy_order_id=out.get("buy_order_id"),
    )
    if existing:
        out["bag_id"] = existing
        if not out.get("buy_order_id") and ":" in existing:
            out["buy_order_id"] = existing.split(":", 1)[1]
        return out

    if side == "BUY":
        bid = make_bag_id(pair, out.get("order_id") or out.get("buy_order_id"))
        if bid:
            out["bag_id"] = bid
            if not out.get("buy_order_id"):
                out["buy_order_id"] = normalize_order_id(
                    out.get("order_id") or out.get("buy_order_id")
                )
    return out


def bag_id_from_registry_row(row: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(row, Mapping):
        return None
    return coerce_bag_id(
        bag_id=row.get("bag_id"),
        pair=row.get("pair"),
        buy_order_id=row.get("buy_order_id"),
    )
