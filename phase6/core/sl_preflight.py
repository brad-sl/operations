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

# Coinbase stop-down preview: stop must be below last trade (~market). Stale ledger entries
# above market trigger PREVIEW_STOP_PRICE_ABOVE_LAST_TRADE_PRICE.
ANCHOR_MAX_ABOVE_MARKET = 1.05


def resolve_stop_calc_base(
    pair: str,
    entry_price: float,
    anchor_entry: Optional[float],
    market_px: Optional[float],
) -> Tuple[float, str]:
    """Pick SL % base; rebase to market when anchor is stale vs last trade."""
    calc_base = float(anchor_entry) if anchor_entry and anchor_entry > 0 else float(entry_price or 0)
    reason = "anchor" if anchor_entry and anchor_entry > 0 else "entry"
    if market_px and market_px > 0 and calc_base > market_px * ANCHOR_MAX_ABOVE_MARKET:
        logger.warning(
            "[SL-ANCHOR-REBASE] %s: calc_base $%.4f >> market $%.4f; rebasing to market for stop-down preview",
            pair,
            calc_base,
            market_px,
        )
        calc_base = float(market_px)
        reason = "market_rebase"
    return calc_base, reason


def ensure_stop_below_market(
    exchange: Any,
    pair: str,
    stop_price: float,
    limit_price: float,
    market_px: float,
    pct: float,
) -> Tuple[float, float]:
    """If stop is still at/above market, recompute from market * (1 - pct)."""
    if not market_px or market_px <= 0:
        return stop_price, limit_price
    if stop_price < market_px * 0.999:
        return stop_price, limit_price
    meta = exchange.get_product_metadata(pair)
    price_inc = float(meta.get("price_increment", 0.0001))
    calc_base = market_px
    stop_price = calc_base * (1 - pct)
    limit_price = stop_price * 0.995
    stop_price, limit_price, _, _ = quantize_stop_bundle(
        exchange, pair, calc_base, stop_price, limit_price
    )
    logger.warning(
        "[SL-ANCHOR-REBASE] %s: stop was >= market $%.4f; recomputed stop $%.4f limit $%.4f",
        pair,
        market_px,
        stop_price,
        limit_price,
    )
    return stop_price, limit_price


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


def sanitize_reattach_order_id(
    exchange: Any,
    pair: str,
    order_id: Optional[str],
) -> Optional[str]:
    """
    Re-attach must not reuse stale BUY order_ids from prior cycles.
    Only return order_id when the exchange still reports an open/pending buy worth polling.
    """
    if not order_id:
        return None
    if not exchange or not hasattr(exchange, "get_order_fill_details"):
        return None
    try:
        fill = exchange.get_order_fill_details(order_id) or {}
        status = str(fill.get("status") or fill.get("order_status") or "").upper()
        filled = float(fill.get("filled_size", fill.get("filled", 0)) or 0)
        if filled > 0 or status in ("FILLED", "DONE", "COMPLETED"):
            return None
        if status in ("CANCELLED", "CANCELED", "EXPIRED", "FAILED", "REJECTED"):
            return None
        if filled <= 0 and not status:
            logger.info(
                "[SL-PREFLIGHT] Dropping stale/unverifiable order_id %s for %s re-attach; using balance_stable poll",
                order_id,
                pair,
            )
            return None
        return str(order_id)
    except Exception as exc:
        logger.debug("[SL-PREFLIGHT] order_id sanitize failed for %s: %s", pair, exc)
        return None


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