"""Resolve sl_attached on live BUY rows from exchange protective orders when attach flags lie."""
from __future__ import annotations

from typing import Any, Dict, Optional


def enrich_buy_sl_truth(
    result: Dict[str, Any],
    stop_loss_manager: Any = None,
) -> Dict[str, Any]:
    """Align sl_attached with platform protective orders when attach reported false."""
    side = str(result.get("side") or result.get("action") or "").upper()
    if side != "BUY" or not result.get("success"):
        return result
    if result.get("sl_attached") is True:
        return result
    pair = result.get("pair")
    if not pair or not stop_loss_manager:
        return result
    try:
        active = stop_loss_manager.detect_active_protective_orders([pair]) or {}
        orders = active.get(pair) or []
        if orders:
            result["sl_attached"] = True
            result["sl_truth_source"] = "exchange_protective_order"
    except Exception:
        pass
    return result