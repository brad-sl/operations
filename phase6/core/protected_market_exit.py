"""
Protected market exit — single place for the Coinbase stop-hold dance.

Why this exists
---------------
Open stop-limits **lock** base size. A market sell that ignores that either:
  - fails with INSUFFICIENT_FUND, or
  - only sells dust free size while the bag stays locked.

Every live exit path (TP, lifecycle dual-peak, operator trim, dust when needed)
must use the same sequence:

  1. cancel open stops for pair
  2. poll until free size settles (Coinbase lags a few seconds)
  3. size + quantize sell qty
  4. place_market_sell
  5. on success: reattach SL on remainder (or cancel-only if flat)
     on fail after cancel: reattach immediately (never leave naked bag)

Decision logic (should we exit? how much?) stays upstream.
This module only owns **execution mechanics**.

Incident class: BTC 2026-08-26 dual_peak miss + dust fill + false manual cash hold.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x if x is not None else default)
    except (TypeError, ValueError):
        return float(default)


def free_base_qty(exchange: Any, pair: str) -> float:
    """Exchange free (unlocked) base size for pair."""
    if exchange is None or not pair:
        return 0.0
    base = str(pair).split("-")[0]
    qty = 0.0
    try:
        if hasattr(exchange, "get_crypto_available"):
            qty = _f(exchange.get_crypto_available(base), 0.0)
        if qty <= 0 and hasattr(exchange, "get_available_balance"):
            qty = _f(exchange.get_available_balance(base), 0.0)
        if qty <= 0 and hasattr(exchange, "get_account_balance"):
            bal = exchange.get_account_balance(base)
            if isinstance(bal, dict):
                qty = _f(bal.get("available") or bal.get("free") or bal.get("balance"), 0.0)
            else:
                qty = _f(bal, 0.0)
    except Exception:
        qty = 0.0
    return max(0.0, qty)


def cancel_stops_and_resolve_base(
    exchange: Any,
    pair: str,
    *,
    qty_full_hint: float = 0.0,
    poll_timeout: float = 4.0,
    lag_poll_timeout: float = 6.0,
) -> Dict[str, Any]:
    """
    Cancel open stops, poll free size, fall back to qty_full_hint if free still lags.

    Returns dict: cancelled, free_qty, base_qty, used_hint_fallback
    """
    out: Dict[str, Any] = {
        "pair": pair,
        "cancelled": 0,
        "free_qty": 0.0,
        "base_qty": 0.0,
        "qty_full_hint": max(0.0, _f(qty_full_hint, 0.0)),
        "used_hint_fallback": False,
        "cancel_error": None,
    }
    if exchange is None or not pair:
        out["error"] = "no_exchange_or_pair"
        return out

    try:
        from phase6.core.sl_preflight import cancel_open_stops_for_pair, poll_available_after_cancel

        out["cancelled"] = int(cancel_open_stops_for_pair(exchange, pair) or 0)
        try:
            poll_available_after_cancel(exchange, pair, timeout=float(poll_timeout))
        except Exception:
            time.sleep(0.8)
    except Exception as ce:
        out["cancel_error"] = str(ce)[:160]
        logger.warning("[PROTECTED-EXIT] cancel stops %s: %s", pair, ce)

    free = free_base_qty(exchange, pair)
    hint = max(0.0, _f(qty_full_hint, 0.0))

    # Coinbase often lags hold release after cancel (BTC 2026-08-26 class).
    if out["cancelled"] and hint > 0 and free > 0 and free < hint * 0.5:
        try:
            from phase6.core.sl_preflight import poll_available_after_cancel

            poll_available_after_cancel(exchange, pair, timeout=float(lag_poll_timeout))
            free2 = free_base_qty(exchange, pair)
            if free2 > free:
                free = free2
        except Exception as pe:
            logger.warning("[PROTECTED-EXIT] free re-poll %s: %s", pair, pe)
        if free < hint * 0.5:
            logger.warning(
                "[PROTECTED-EXIT] free_qty %.8f << qty_full %.8f after cancel; "
                "using qty_full for base %s",
                free,
                hint,
                pair,
            )
            free = hint
            out["used_hint_fallback"] = True
    elif free <= 0 and hint > 0:
        free = hint
        out["used_hint_fallback"] = True

    out["free_qty"] = float(free)
    out["base_qty"] = float(free if free > 0 else hint)
    return out


def reattach_stop_after_exit(
    exchange: Any,
    pair: str,
    *,
    entry_price: float,
    remaining_qty_hint: float = 0.0,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Cancel any leftover stops, resolve remaining free size, attach SL on remainder.
    Safe no-op when remaining size is zero.
    """
    out: Dict[str, Any] = {
        "pair": pair,
        "ok": False,
        "action": "reattach",
        "entry_price": entry_price,
        "size": 0.0,
    }
    if exchange is None or not pair:
        out["error"] = "no_exchange_or_pair"
        return out
    try:
        from phase6.core.config_loader import ConfigLoader
        from phase6.core.sl_preflight import (
            cancel_open_stops_for_pair,
            poll_available_after_cancel,
            resolve_sl_attach_size,
        )
        from phase6.core.stop_loss_manager import StopLossManager

        cfg = config_dict
        if not cfg:
            try:
                cfg = ConfigLoader()._config
            except Exception:
                cfg = json.loads(Path("config/trading_config_phase6.json").read_text())

        try:
            out["cancelled"] = int(cancel_open_stops_for_pair(exchange, pair) or 0)
        except Exception as ce:
            out["cancel_error"] = str(ce)[:160]
            out["cancelled"] = 0

        try:
            poll_available_after_cancel(exchange, pair, timeout=4.0)
        except Exception:
            time.sleep(0.8)

        hint = max(0.0, _f(remaining_qty_hint, 0.0))
        size, meta = resolve_sl_attach_size(exchange, pair, hint if hint > 0 else 1e9)
        out["resolve_meta"] = (
            {k: meta.get(k) for k in list(meta or {})[:12]} if isinstance(meta, dict) else {}
        )
        if size <= 0 and hint > 0:
            size = hint
            try:
                if hasattr(exchange, "quantize_size"):
                    size = float(exchange.quantize_size(pair, size))
            except Exception:
                pass
        out["size"] = float(size or 0.0)
        if size <= 0:
            out["error"] = "no_remaining_size"
            out["ok"] = True
            out["action"] = "skip_empty"
            return out

        anchor = _f(entry_price, 0.0)
        if anchor <= 0:
            try:
                anchor = _f(exchange.get_price(pair), 0.0)
            except Exception:
                anchor = 0.0
        if anchor <= 0:
            out["error"] = "no_entry_anchor"
            return out
        out["entry_price"] = anchor

        slm = StopLossManager(exchange, cfg if isinstance(cfg, dict) else {}, mode="live")
        ok = bool(
            slm.attach_stop_loss(
                pair,
                anchor,
                float(size),
                fresh_buy=False,
            )
        )
        out["ok"] = ok
        if not ok:
            out["error"] = "attach_stop_loss_returned_false"
        else:
            logger.info(
                "[PROTECTED-EXIT] SL reattached %s size=%.8f anchor=%.6f",
                pair,
                size,
                anchor,
            )
        return out
    except Exception as e:
        out["error"] = str(e)[:200]
        logger.error("[PROTECTED-EXIT] SL reattach exception %s: %s", pair, e)
        return out


def _ledger_sell(
    *,
    pair: str,
    qty: float,
    exit_price: float,
    order_id: Optional[str],
    reason: str,
    signal_source: str,
    entry_price: float = 0.0,
) -> Optional[str]:
    try:
        from phase6.core.trade_ledger import TradeLedger

        row: Dict[str, Any] = {
            "pair": pair,
            "side": "SELL",
            "action": "SELL",
            "qty": qty,
            "exit_price": exit_price,
            "order_id": order_id,
            "reason": reason,
            "signal_source": signal_source or reason,
            "success": True,
        }
        if entry_price > 0:
            row["entry_price"] = entry_price
        TradeLedger().log_trade(row)
        return None
    except Exception as e:
        return str(e)[:120]


def protected_market_exit(
    exchange: Any,
    pair: str,
    *,
    qty: Optional[float] = None,
    frac: Optional[float] = None,
    qty_full_hint: float = 0.0,
    entry_price: float = 0.0,
    mark_price: float = 0.0,
    reason: str = "protected_exit",
    signal_source: str = "",
    dry_run: bool = False,
    ledger: bool = True,
    reattach_sl: bool = True,
    config_dict: Optional[Dict[str, Any]] = None,
    poll_timeout: float = 4.0,
    cancel_stops: bool = True,
) -> Dict[str, Any]:
    """
    Execute one protected market sell.

    Sizing
    ------
    - If ``qty`` is set: sell that absolute size (clamped to base after unlock).
    - Else if ``frac`` is set: sell ``base_qty * frac`` (0..1).
    - Else: sell full ``base_qty`` (flat exit).

    Returns a result dict with success, order_id, filled_qty, sl_reattach, etc.
    Never raises for normal exchange failures — encodes them in the dict.
    """
    result: Dict[str, Any] = {
        "ts": _utcnow(),
        "pair": pair,
        "success": False,
        "dry_run": bool(dry_run),
        "reason": reason,
        "signal_source": signal_source or reason,
        "qty_requested": qty,
        "frac": frac,
    }
    if exchange is None or not pair:
        result["error"] = "no_exchange_or_pair"
        return result

    # 1–2 unlock + resolve base
    if cancel_stops:
        resolved = cancel_stops_and_resolve_base(
            exchange,
            pair,
            qty_full_hint=qty_full_hint,
            poll_timeout=poll_timeout,
        )
    else:
        free = free_base_qty(exchange, pair)
        hint = max(0.0, _f(qty_full_hint, 0.0))
        resolved = {
            "cancelled": 0,
            "free_qty": free,
            "base_qty": free if free > 0 else hint,
            "used_hint_fallback": free <= 0 and hint > 0,
            "qty_full_hint": hint,
        }
    result["cancelled_stops"] = int(resolved.get("cancelled") or 0)
    result["free_qty"] = _f(resolved.get("free_qty"), 0.0)
    result["base_qty"] = _f(resolved.get("base_qty"), 0.0)
    result["used_hint_fallback"] = bool(resolved.get("used_hint_fallback"))
    if resolved.get("cancel_error"):
        result["cancel_error"] = resolved["cancel_error"]

    base_qty = _f(result["base_qty"], 0.0)
    sell_qty = 0.0
    if qty is not None and _f(qty, 0.0) > 0:
        sell_qty = min(_f(qty, 0.0), base_qty) if base_qty > 0 else _f(qty, 0.0)
    elif frac is not None:
        f = max(0.0, min(1.0, _f(frac, 0.0)))
        sell_qty = base_qty * f
        result["frac"] = f
    else:
        sell_qty = base_qty

    try:
        if hasattr(exchange, "quantize_size"):
            sell_qty = float(exchange.quantize_size(pair, sell_qty))
    except Exception:
        sell_qty = round(sell_qty, 8)
    result["qty"] = sell_qty

    def _restore_sl(hint_rem: float, tag: str) -> None:
        if not reattach_sl:
            return
        try:
            sl_info = reattach_stop_after_exit(
                exchange,
                pair,
                entry_price=entry_price if entry_price > 0 else mark_price,
                remaining_qty_hint=hint_rem,
                config_dict=config_dict,
            )
            result[tag] = sl_info
        except Exception as e:
            result[tag] = {"ok": False, "error": str(e)[:120]}

    if sell_qty <= 0:
        result["skipped"] = True
        result["skip_reason"] = "zero_qty"
        if result["cancelled_stops"] and (base_qty > 0 or qty_full_hint > 0):
            _restore_sl(base_qty or qty_full_hint, "sl_reattach_after_skip")
        return result

    if dry_run:
        result["success"] = True
        result["skipped"] = False
        result["note"] = "dry_run_no_order"
        return result

    if not hasattr(exchange, "place_market_sell"):
        result["error"] = "no_place_market_sell"
        if result["cancelled_stops"]:
            _restore_sl(base_qty or qty_full_hint, "sl_reattach_after_fail")
        return result

    # 3–4 sell
    try:
        raw = exchange.place_market_sell(pair, sell_qty) or {}
    except Exception as se:
        result["error"] = str(se)[:200]
        logger.error("[PROTECTED-EXIT] sell exception %s: %s", pair, se)
        if result["cancelled_stops"] or cancel_stops:
            _restore_sl(base_qty or qty_full_hint, "sl_reattach_after_fail")
        return result

    ok = bool(raw.get("success"))
    oid = raw.get("order_id") or raw.get("id")
    result["success"] = ok
    result["order_id"] = oid
    if not ok:
        result["error"] = raw.get("error")
        logger.warning("[PROTECTED-EXIT] sell failed %s: %s", pair, result.get("error"))
        if result["cancelled_stops"] or cancel_stops:
            _restore_sl(base_qty or qty_full_hint, "sl_reattach_after_fail")
        return result

    # Fill details
    exit_px = _f(mark_price, 0.0)
    filled = sell_qty
    if oid and hasattr(exchange, "get_order_fill_details"):
        try:
            time.sleep(0.5)
            fill = exchange.get_order_fill_details(oid) or {}
            if _f(fill.get("average_filled_price")) > 0:
                exit_px = _f(fill["average_filled_price"])
            if _f(fill.get("filled_size")) > 0:
                filled = _f(fill["filled_size"])
        except Exception:
            pass
    if exit_px <= 0 and hasattr(exchange, "get_price"):
        try:
            exit_px = _f(exchange.get_price(pair), 0.0)
        except Exception:
            pass
    result["exit_price"] = exit_px
    result["filled_qty"] = filled

    if ledger:
        err = _ledger_sell(
            pair=pair,
            qty=filled,
            exit_price=exit_px,
            order_id=str(oid) if oid else None,
            reason=reason,
            signal_source=signal_source or reason,
            entry_price=_f(entry_price, 0.0),
        )
        if err:
            result["ledger_error"] = err

    # 5 reattach or full-exit cleanup
    rem = max(0.0, base_qty - filled)
    full_flat = (frac is not None and _f(frac, 0.0) >= 0.99) or (
        qty is None and frac is None and rem <= 1e-12
    ) or (base_qty > 0 and filled >= base_qty * 0.99)
    result["remaining_qty_hint"] = rem
    result["full_flat"] = bool(full_flat)

    if reattach_sl:
        if full_flat or rem <= 1e-12:
            try:
                from phase6.core.sl_preflight import cancel_open_stops_for_pair

                cancel_open_stops_for_pair(exchange, pair)
                result["sl_reattach"] = {"ok": True, "action": "cancelled_full_exit"}
            except Exception as ce:
                result["sl_reattach"] = {"ok": False, "error": f"cancel_full: {ce}"[:160]}
        else:
            sl_info = reattach_stop_after_exit(
                exchange,
                pair,
                entry_price=entry_price if entry_price > 0 else exit_px,
                remaining_qty_hint=rem,
                config_dict=config_dict,
            )
            result["sl_reattach"] = sl_info
            if not sl_info.get("ok"):
                logger.warning(
                    "[PROTECTED-EXIT] SL reattach failed %s: %s",
                    pair,
                    sl_info.get("error") or sl_info,
                )

    logger.info(
        "[PROTECTED-EXIT] LIVE %s qty=%.8f oid=%s reason=%s sl=%s",
        pair,
        filled,
        oid,
        reason,
        (result.get("sl_reattach") or {}).get("ok"),
    )
    return result
