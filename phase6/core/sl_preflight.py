"""
ANALYST-20260705-005 / 007: SL pre-flight settlement + tick precision helpers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Spec: 2-3s for low-risk re-attach; longer when order_id ties to fresh buy
LOW_RISK_TIMEOUT = 2.5
MEDIUM_RISK_TIMEOUT = 3.5
HIGH_RISK_TIMEOUT = 5.0
ORDER_FILL_TIMEOUT = 20.0


def settlement_poll_params(
    pair: str,
    *,
    order_id: Optional[str] = None,
    risk_level: str = "LOW",
) -> Dict[str, Any]:
    """Risk-aware poll configuration (sl_risk_scorer levels)."""
    level = (risk_level or "LOW").upper()
    if order_id:
        return {"timeout": ORDER_FILL_TIMEOUT, "order_id": order_id, "mode": "order_fill"}
    if level in ("HIGH", "CRITICAL"):
        return {"timeout": HIGH_RISK_TIMEOUT, "order_id": None, "mode": "balance_stable"}
    if level == "MEDIUM":
        return {"timeout": MEDIUM_RISK_TIMEOUT, "order_id": None, "mode": "balance_stable"}
    return {"timeout": LOW_RISK_TIMEOUT, "order_id": None, "mode": "balance_stable"}


def quantize_stop_bundle(
    exchange: Any,
    pair: str,
    calc_base: float,
    stop_price: float,
    limit_price: float,
) -> Tuple[float, float, str, str]:
    """
    Apply per-product tick rules; ensure stop < base and limit < stop.
    Returns (stop_f, limit_f, stop_str, limit_str).
    """
    meta = exchange.get_product_metadata(pair)
    price_inc = float(meta.get("price_increment", 0.0001))

    stop_str = exchange.quantize_price(pair, stop_price)
    stop_f = float(stop_str)
    limit_str = exchange.quantize_price(pair, limit_price)
    limit_f = float(limit_str)

    if stop_f >= calc_base:
        logger.warning(f"[SL-PREFLIGHT] stop {stop_f} >= base {calc_base} for {pair}; nudge by tick")
        stop_f = float(exchange.quantize_price(pair, calc_base - price_inc))
        limit_f = float(exchange.quantize_price(pair, stop_f - price_inc))
        stop_str = exchange.quantize_price(pair, stop_f)
        limit_str = exchange.quantize_price(pair, limit_f)

    if limit_f >= stop_f:
        limit_f = float(exchange.quantize_price(pair, stop_f - price_inc))
        limit_str = exchange.quantize_price(pair, limit_f)

    return stop_f, limit_f, stop_str, limit_str