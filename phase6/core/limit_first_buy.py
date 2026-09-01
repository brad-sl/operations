#!/usr/bin/env python3
"""Limit-first buy policy helpers (pure + wait loop). Default path remains market IOC.

Brad decisions 2026-08-31:
  unfilled → skip (no market fallback)
  pilot universe → full basket (when enabled)
  fill_wait_s → 45
  Phase A/B only — enabled flag default False

See docs/design/LIMIT_FIRST_BUY_DESIGN.md
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Sequence


# Locked defaults (design §4.2 + Brad answers)
DEFAULT_FILL_WAIT_S = 45.0
DEFAULT_POLL_INTERVAL_S = 2.0
DEFAULT_MIN_FILL_USD = 10.0
DEFAULT_POST_ONLY = True
DEFAULT_PRICE_REF = "bid"
DEFAULT_MARKET_FALLBACK = False  # skip
DEFAULT_MAX_REQUOTES = 0
DEFAULT_ELEVATED_TAPE = "abort"


@dataclass
class LimitFirstPolicy:
    enabled: bool = False  # HARD default off
    post_only: bool = DEFAULT_POST_ONLY
    price_ref: str = DEFAULT_PRICE_REF  # bid | mid | ask
    offset_bps: float = 0.0
    fill_wait_s: float = DEFAULT_FILL_WAIT_S
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    min_fill_usd: float = DEFAULT_MIN_FILL_USD
    market_fallback: bool = DEFAULT_MARKET_FALLBACK
    max_requotes: int = DEFAULT_MAX_REQUOTES
    elevated_tape_policy: str = DEFAULT_ELEVATED_TAPE  # abort | allow
    pilot_max_buys_per_day: int = 0  # 0 = no pilot cap when enabled (full basket)
    pilot_max_usd_per_day: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def policy_from_config(cfg: Optional[dict] = None) -> LimitFirstPolicy:
    """Read entry_execution.limit_first; always default enabled=False."""
    cfg = cfg if isinstance(cfg, dict) else {}
    ee_raw = cfg.get("entry_execution")
    ee: dict = ee_raw if isinstance(ee_raw, dict) else {}
    if not ee:
        gs = cfg.get("global_settings")
        if isinstance(gs, dict):
            ee_gs = gs.get("entry_execution")
            ee = ee_gs if isinstance(ee_gs, dict) else {}
    lf_raw = ee.get("limit_first") if ee else None
    lf: dict = lf_raw if isinstance(lf_raw, dict) else {}
    mode = str(ee.get("mode") or "market_ioc").lower() if ee else "market_ioc"
    explicit_on = bool(lf.get("enabled", False))
    # Hard fence: require explicit enabled true AND mode limit_first*
    enabled = explicit_on and mode in ("limit_first", "limit_first_v1")
    return LimitFirstPolicy(
        enabled=enabled,
        post_only=bool(lf.get("post_only", DEFAULT_POST_ONLY)),
        price_ref=str(lf.get("price_ref", DEFAULT_PRICE_REF) or DEFAULT_PRICE_REF).lower(),
        offset_bps=float(lf.get("offset_bps", 0) or 0),
        fill_wait_s=float(lf.get("fill_wait_s", DEFAULT_FILL_WAIT_S) or DEFAULT_FILL_WAIT_S),
        poll_interval_s=float(
            lf.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S) or DEFAULT_POLL_INTERVAL_S
        ),
        min_fill_usd=float(lf.get("min_fill_usd", DEFAULT_MIN_FILL_USD) or DEFAULT_MIN_FILL_USD),
        market_fallback=bool(lf.get("market_fallback", DEFAULT_MARKET_FALLBACK)),
        max_requotes=int(lf.get("max_requotes", DEFAULT_MAX_REQUOTES) or 0),
        elevated_tape_policy=str(
            lf.get("elevated_tape", lf.get("elevated_tape_policy", DEFAULT_ELEVATED_TAPE))
        ),
        pilot_max_buys_per_day=int(lf.get("pilot_max_buys_per_day", 0) or 0),
        pilot_max_usd_per_day=float(lf.get("pilot_max_usd_per_day", 0) or 0),
    )


def limit_price_from_refs(
    *,
    bid: Optional[float],
    ask: Optional[float],
    last: Optional[float],
    price_ref: str = "bid",
    offset_bps: float = 0.0,
) -> Optional[float]:
    """Compute buy limit price. Pure."""
    ref = (price_ref or "bid").lower()
    px = None
    if ref == "bid" and bid and bid > 0:
        px = float(bid)
    elif ref == "ask" and ask and ask > 0:
        px = float(ask)
    elif ref == "mid":
        if bid and ask and bid > 0 and ask > 0:
            px = (float(bid) + float(ask)) / 2.0
        elif last and last > 0:
            px = float(last)
    elif last and last > 0:
        px = float(last)
    elif bid and bid > 0:
        px = float(bid)
    if px is None or px <= 0:
        return None
    if offset_bps:
        # negative bps = more passive (lower buy price)
        px = px * (1.0 + float(offset_bps) / 10000.0)
    return px


def base_size_from_usd(usd_amount: float, limit_price: float) -> Optional[float]:
    if usd_amount <= 0 or limit_price <= 0:
        return None
    return float(usd_amount) / float(limit_price)


def order_is_terminal(status: str) -> bool:
    s = (status or "").upper()
    return s in {
        "FILLED",
        "CANCELLED",
        "CANCELED",
        "EXPIRED",
        "FAILED",
        "REJECTED",
    }


def order_is_open(status: str) -> bool:
    s = (status or "").upper()
    return s in {"OPEN", "PENDING", "QUEUED", "ACTIVE"} or s == ""


def classify_fill(
    *,
    filled_size: float,
    avg_price: float,
    min_fill_usd: float,
) -> str:
    """full | partial | none"""
    notional = float(filled_size or 0) * float(avg_price or 0)
    if notional >= float(min_fill_usd) and filled_size > 0 and avg_price > 0:
        # caller may still distinguish full vs partial via requested size
        return "filled"
    return "none"


def wait_for_limit_fill(
    exchange: Any,
    order_id: str,
    *,
    fill_wait_s: float = DEFAULT_FILL_WAIT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> Dict[str, Any]:
    """Poll order until terminal, timeout, or fill. Does not cancel (caller cancels)."""
    started = monotonic_fn()
    last: Dict[str, Any] = {
        "order_id": order_id,
        "status": "",
        "filled_size": 0.0,
        "average_filled_price": 0.0,
        "timed_out": False,
        "polls": 0,
    }
    while True:
        last["polls"] += 1
        det = {}
        if hasattr(exchange, "get_order_fill_details"):
            det = exchange.get_order_fill_details(order_id) or {}
        status = str(det.get("status") or "")
        filled = float(det.get("filled_size") or 0)
        avg = float(det.get("average_filled_price") or 0)
        last.update(
            {
                "status": status,
                "filled_size": filled,
                "average_filled_price": avg,
            }
        )
        if filled > 0 and avg > 0 and order_is_terminal(status):
            last["timed_out"] = False
            return last
        if filled > 0 and avg > 0 and not order_is_open(status) and status:
            return last
        # Partial while still open: keep waiting until timeout
        if order_is_terminal(status) and status.upper() in {"FILLED"}:
            return last
        if order_is_terminal(status) and filled <= 0:
            return last
        elapsed = monotonic_fn() - started
        if elapsed >= float(fill_wait_s):
            last["timed_out"] = True
            return last
        sleep_fn(float(poll_interval_s))


def cancel_and_recheck(exchange: Any, order_id: str) -> Dict[str, Any]:
    """Cancel then re-fetch fill (race-safe)."""
    cancelled = False
    if hasattr(exchange, "cancel_order"):
        try:
            cancelled = bool(exchange.cancel_order(order_id))
        except Exception:
            cancelled = False
    det = {}
    if hasattr(exchange, "get_order_fill_details"):
        det = exchange.get_order_fill_details(order_id) or {}
    return {
        "cancelled": cancelled,
        "status": det.get("status"),
        "filled_size": float(det.get("filled_size") or 0),
        "average_filled_price": float(det.get("average_filled_price") or 0),
    }
