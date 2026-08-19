"""Registry of attached protective stop orders (pair → entry basis for fill reconciliation)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.paths import PROJECT_ROOT

REGISTRY_PATH = PROJECT_ROOT / "data/state/protective_orders_registry.jsonl"


def _ensure_parent() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)


def register_protective_order(
    *,
    pair: str,
    sl_order_id: str,
    entry_price: float,
    qty: float,
    stop_price: float,
    limit_price: Optional[float] = None,
    buy_order_id: Optional[str] = None,
    mode: str = "live",
    sleeve: str = "crypto",
    reason: Optional[str] = None,
) -> None:
    if not sl_order_id or not pair:
        return
    _ensure_parent()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pair": pair,
        "sl_order_id": sl_order_id,
        "entry_price": float(entry_price),
        "qty": float(qty),
        "stop_price": float(stop_price),
        "limit_price": float(limit_price) if limit_price is not None else None,
        "buy_order_id": buy_order_id,
        "mode": mode,
        "sleeve": sleeve or "crypto",
        "reason": reason,
        "status": "open",
    }
    with open(REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def open_preserve_order_ids() -> List[str]:
    """Latest open preserve-sleeve order ids from registry."""
    rows = load_all_registry_rows()
    open_ids: Dict[str, str] = {}
    for row in rows:
        oid = row.get("sl_order_id")
        if not oid:
            continue
        if row.get("status") == "closed":
            open_ids.pop(str(oid), None)
            continue
        if str(row.get("sleeve") or "").lower() == "preserve" or str(row.get("reason") or "") == "preserve_e1":
            open_ids[str(oid)] = str(oid)
    return list(open_ids.values())


def mark_sl_filled(sl_order_id: str) -> None:
    """Append status=closed marker (append-only audit)."""
    if not sl_order_id or not REGISTRY_PATH.exists():
        return
    _ensure_parent()
    # Find latest open row for this id
    match: Optional[Dict[str, Any]] = None
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("sl_order_id") == sl_order_id and row.get("status") != "closed":
                match = row
    if not match:
        return
    match = dict(match)
    match["status"] = "closed"
    match["closed_at"] = datetime.now(timezone.utc).isoformat()
    with open(REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(match) + "\n")


def lookup_entry_for_pair(sl_order_id: Optional[str], pair: str) -> Optional[Dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return None
    best: Optional[Dict[str, Any]] = None
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if sl_order_id and row.get("sl_order_id") == sl_order_id:
                return row
            if row.get("pair") == pair and row.get("status") != "closed":
                best = row
    return best


def load_all_registry_rows() -> List[Dict[str, Any]]:
    if not REGISTRY_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out