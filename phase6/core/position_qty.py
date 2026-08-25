"""
EXIT-H5 — Position qty SSOT helpers.

phase6_live_state historically used ``amount`` only. Exit paths (lifecycle, TP, SL)
often look for ``qty`` / ``quantity``. Readers must accept all three; writers must
emit all three so residual bags never go uncovered on a key mismatch.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Union


def position_qty(row: Any, default: float = 0.0) -> float:
    """Extract base size from a position row or raw number."""
    if row is None:
        return float(default)
    if isinstance(row, (int, float)):
        try:
            return float(row)
        except (TypeError, ValueError):
            return float(default)
    if not isinstance(row, Mapping):
        return float(default)
    for key in ("qty", "quantity", "amount", "size", "base_size"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 0 or key in ("qty", "quantity", "amount"):
            return v
    return float(default)


def normalize_position_row(row: MutableMapping[str, Any]) -> Dict[str, Any]:
    """
    In-place + return: ensure amount/qty/quantity are consistent aliases.
    Prefer existing positive qty, else amount, else quantity.
    """
    if not isinstance(row, MutableMapping):
        return {}
    q = position_qty(row, 0.0)
    # Keep zero dust rows honest
    row["amount"] = q
    row["qty"] = q
    row["quantity"] = q
    return dict(row)


def normalize_positions_list(
    positions: Optional[Iterable[Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in positions or []:
        if not isinstance(row, MutableMapping):
            continue
        normalize_position_row(row)
        out.append(dict(row))
    return out


def qty_map_from_live_state(live: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    """pair -> qty from phase6_live_state-shaped dict."""
    out: Dict[str, float] = {}
    if not isinstance(live, Mapping):
        return out
    rows = live.get("positions") or live.get("trading_positions") or []
    if isinstance(rows, Mapping):
        # flat map form
        for k, v in rows.items():
            if str(k) in ("USD", "USDC", "verified", "error", "value_usd", "positions"):
                continue
            pair = str(k) if str(k).endswith("-USD") else f"{k}-USD"
            q = position_qty(v)
            if q > 0:
                out[pair] = q
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        pair = str(row.get("pair") or "")
        if not pair:
            continue
        q = position_qty(row)
        if q > 0:
            out[pair] = q
    return out


def ensure_live_state_qty_aliases(path: Union[str, Any]) -> Dict[str, Any]:
    """
    Rewrite phase6_live_state.json so every position has amount/qty/quantity.
    Returns summary {n, path, updated}.
    """
    from pathlib import Path
    import json
    from datetime import datetime, timezone

    p = Path(path)
    summary: Dict[str, Any] = {"path": str(p), "n": 0, "updated": False}
    if not p.exists():
        summary["error"] = "missing"
        return summary
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        summary["error"] = str(e)[:160]
        return summary
    changed = False
    for key in ("positions", "trading_positions"):
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            before = (row.get("amount"), row.get("qty"), row.get("quantity"))
            normalize_position_row(row)
            after = (row.get("amount"), row.get("qty"), row.get("quantity"))
            if before != after:
                changed = True
            summary["n"] += 1
    if changed:
        data["qty_ssot"] = {
            "schema": "position_qty_v1",
            "updated": datetime.now(timezone.utc).isoformat(),
            "aliases": ["amount", "qty", "quantity"],
        }
        p.write_text(json.dumps(data, indent=2) + "\n")
        summary["updated"] = True
    return summary
