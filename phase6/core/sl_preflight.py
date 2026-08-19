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

# ENG-S3-02: authoritative post-buy settlement + fill wait lives in stop_loss_manager.attach_stop_loss
# via exchange.poll_for_settlement(order_id=...). order_executor must not run parallel fill polls.
SETTLEMENT_POLL_OWNER = "stop_loss_manager.attach_stop_loss"


def fetch_verified_order_fill(exchange: Any, order_id: Optional[str]) -> Dict[str, Any]:
    """
    Read fill price/size from the exchange after settlement poll (single source of fill truth).
    Returns fill_verified=True only when both average_filled_price and filled_size are > 0.
    """
    out: Dict[str, Any] = {
        "average_filled_price": 0.0,
        "filled_size": 0.0,
        "status": "",
        "fill_verified": False,
    }
    if not order_id or not exchange or not hasattr(exchange, "get_order_fill_details"):
        return out
    try:
        fill = exchange.get_order_fill_details(order_id) or {}
        fp = float(fill.get("average_filled_price") or fill.get("filled_price") or 0)
        fs = float(fill.get("filled_size") or fill.get("filled") or 0)
        out["average_filled_price"] = fp
        out["filled_size"] = fs
        out["status"] = str(fill.get("status") or fill.get("order_status") or "")
        out["fill_verified"] = fp > 0 and fs > 0
    except Exception as exc:
        logger.debug("[SL-PREFLIGHT] fetch_verified_order_fill failed for %s: %s", order_id, exc)
    return out


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
    meta = exchange.get_product_metadata(pair)
    price_inc = float(meta.get("price_increment", 0.0001))
    buffer_px = max(price_inc, market_px * 0.0001)
    if stop_price < market_px - buffer_px:
        return stop_price, limit_price
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


def order_configuration_is_stop(oc: Optional[Dict[str, Any]]) -> bool:
    """Coinbase Advanced Trade uses keys like stop_limit_stop_limit_gtc (not bare stop_limit)."""
    if not oc:
        return False
    for key in oc.keys():
        kl = str(key).lower()
        if kl.startswith("stop_limit") or kl.startswith("stop_market") or kl.startswith("trigger_bracket"):
            return True
        if "stop" in kl and "bracket" not in kl:
            return True
    return False


def extract_stop_price_from_order(order: Dict[str, Any]) -> Optional[float]:
    oc = order.get("order_configuration") or {}
    for key, cfg in oc.items():
        if not isinstance(cfg, dict):
            continue
        if "stop" in str(key).lower():
            sp = cfg.get("stop_price") or cfg.get("stop_trigger_price")
            if sp is not None:
                try:
                    return float(sp)
                except (TypeError, ValueError):
                    pass
    if order.get("stop_price") is not None:
        try:
            return float(order["stop_price"])
        except (TypeError, ValueError):
            pass
    return None


def cancel_open_stops_for_pair(exchange: Any, pair: str) -> int:
    """Cancel open protective stops so base balance is released for re-attach."""
    canceled = 0
    if not hasattr(exchange, "get_open_stop_orders"):
        orders = exchange.get_open_orders(pair) or []
        orders = [o for o in orders if order_configuration_is_stop(o.get("order_configuration"))]
    else:
        orders = exchange.get_open_stop_orders(pair) or []
    for order in orders:
        oid = order.get("order_id") or order.get("id")
        if not oid:
            continue
        try:
            if exchange.cancel_order(oid):
                canceled += 1
                logger.info("[SL-RELEASE] Canceled stop %s for %s", oid, pair)
        except Exception as exc:
            logger.warning("[SL-RELEASE] Cancel failed %s %s: %s", pair, oid, exc)
    return canceled


def poll_available_after_cancel(exchange: Any, pair: str, timeout: float = 4.0) -> float:
    """Wait for tradable balance after stop cancel (hold release lag)."""
    import time

    asset = pair.split("-")[0] if "-" in pair else pair
    if not hasattr(exchange, "get_crypto_available"):
        return 0.0
    deadline = time.time() + timeout
    last = 0.0
    while time.time() < deadline:
        try:
            last = float(exchange.get_crypto_available(asset) or 0.0)
            if last > 0:
                return last
        except Exception:
            pass
        time.sleep(0.35)
    return last


def resolve_sl_attach_size(
    exchange: Any,
    pair: str,
    requested_size: float,
    *,
    safety_ratio: float = 0.98,
) -> Tuple[float, Dict[str, Any]]:
    """
    Size stop attachment to tradable (available) balance, not ledger/holdings total.
    Returns (effective_size, meta). effective_size 0 => caller should skip or release holds first.
    """
    meta: Dict[str, Any] = {"requested": requested_size, "pair": pair}
    asset = pair.split("-")[0] if "-" in pair else pair
    avail = 0.0
    total = 0.0
    try:
        if hasattr(exchange, "get_crypto_available"):
            avail = float(exchange.get_crypto_available(asset) or 0.0)
        if hasattr(exchange, "get_holdings_verified"):
            hv = exchange.get_holdings_verified() or {}
            total = float((hv.get("positions") or {}).get(asset, 0.0) or 0.0)
    except Exception as exc:
        meta["balance_error"] = str(exc)

    meta["available"] = avail
    meta["total"] = total

    effective = float(requested_size or 0.0)
    if effective <= 0 and total > 0:
        effective = total

    if avail <= 0 and total > 0:
        meta["holds_entire_balance"] = True
        meta["hint"] = "cancel_existing_stops_before_attach"
        return 0.0, meta

    cap = max(0.0, avail * safety_ratio)
    if effective > cap:
        logger.warning(
            "[SL-SIZE] %s: capping attach size %.8f -> %.8f (avail=%.8f)",
            pair,
            effective,
            cap,
            avail,
        )
        effective = cap
        meta["capped"] = True

    if hasattr(exchange, "quantize_size"):
        q = float(exchange.quantize_size(pair, effective))
        meta["quantized"] = q
        effective = q

    if effective <= 0:
        meta["skip_reason"] = "dust_or_zero_after_quantize"
        return 0.0, meta

    return effective, meta