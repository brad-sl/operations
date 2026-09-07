"""
USD ↔ USDC conversion for park / powder balancer.

Coinbase Advanced Trade on CONSUMER (Trading Bot) portfolios:
  - No spot product USDC-USD / USD-USDC
  - Native Convert API only works on DEFAULT portfolio
  - Move-funds between portfolios needs transfer scopes (often missing)

Working path on this venue: two-hop via USDT spot books that exist:
  USD → USDC:  BUY USDT-USD (quote USD) → SELL USDT-USDC (base USDT → quote USDC)
  USDC → USD:  BUY USDT-USDC (quote USDC) → SELL USDT-USD (base USDT → quote USD)

Native Convert is tried first when available so Default-portfolio keys work without hops.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

USDT_USD = "USDT-USD"
USDT_USDC = "USDT-USDC"
MIN_HOP_USD = 1.0
SETTLE_SLEEP_S = 1.2


def _exchange_from_runner(runner: Any) -> Any:
    for obj in (
        getattr(runner, "exchange", None),
        getattr(getattr(runner, "order_executor", None), "exchange", None),
        getattr(getattr(runner, "trade_executor", None), "exchange", None),
        getattr(getattr(runner, "portfolio", None), "exchange", None),
    ):
        if obj is not None:
            return obj
    return None


def _bal(ex: Any, ccy: str) -> float:
    try:
        v = ex.get_account_balance(ccy)
        return float(v or 0.0)
    except Exception:
        return 0.0


def _ok_order(resp: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(resp, dict):
        return False
    if resp.get("success") is True:
        return True
    if resp.get("success_response") or resp.get("order_id"):
        return True
    return False


def try_native_convert(
    ex: Any,
    *,
    from_ccy: str,
    to_ccy: str,
    amount: float,
) -> Dict[str, Any]:
    """Coinbase Convert quote+commit. Fails on non-default portfolios."""
    amount = float(amount)
    if amount < MIN_HOP_USD:
        return {"success": False, "error": "amount_too_small", "method": "native_convert"}

    sdk = getattr(ex, "sdk_client", None)
    if sdk is None:
        try:
            if hasattr(ex, "_ensure_live_client"):
                ex._ensure_live_client()
            sdk = getattr(ex, "sdk_client", None)
        except Exception:
            sdk = None
    if sdk is None or not hasattr(sdk, "create_convert_quote"):
        return {"success": False, "error": "no_sdk_convert", "method": "native_convert"}

    amt = f"{amount:.2f}"
    try:
        quote = sdk.create_convert_quote(
            from_account=from_ccy,
            to_account=to_ccy,
            amount=amt,
        )
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": "native_convert",
            "stage": "quote",
        }

    trade = getattr(quote, "trade", None) or (quote.get("trade") if isinstance(quote, dict) else None)
    trade_id = None
    if trade is not None:
        trade_id = getattr(trade, "id", None) or (
            trade.get("id") if isinstance(trade, dict) else None
        )
    if not trade_id and isinstance(quote, dict):
        trade_id = (quote.get("trade") or {}).get("id") if isinstance(quote.get("trade"), dict) else quote.get("id")
    if not trade_id:
        return {
            "success": False,
            "error": "no_trade_id_in_quote",
            "method": "native_convert",
            "quote": str(quote)[:500],
        }

    try:
        committed = sdk.commit_convert_trade(
            trade_id=str(trade_id),
            from_account=from_ccy,
            to_account=to_ccy,
        )
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": "native_convert",
            "stage": "commit",
            "trade_id": str(trade_id),
        }

    return {
        "success": True,
        "method": "native_convert",
        "trade_id": str(trade_id),
        "from": from_ccy,
        "to": to_ccy,
        "amount": amount,
        "commit": str(committed)[:400],
    }


def _wait_bal(ex: Any, ccy: str, min_delta: float, before: float, tries: int = 8) -> float:
    """Poll until balance moves or tries exhausted."""
    last = before
    for _ in range(tries):
        time.sleep(SETTLE_SLEEP_S)
        last = _bal(ex, ccy)
        if last - before >= min_delta * 0.5:
            return last
    return last


def _limit_only(ex: Any, product: str) -> bool:
    fn = getattr(ex, "product_is_limit_only", None)
    if callable(fn):
        try:
            return bool(fn(product))
        except Exception:
            pass
    return str(product).upper() == "USDT-USDC"


def _aggressive_bid(ex: Any, product: str) -> float:
    book = {}
    try:
        book = ex.get_best_bid_ask(product) or {}
    except Exception:
        book = {}
    bid = float(book.get("bid") or book.get("last") or 0)
    if bid <= 0:
        try:
            bid = float(ex.get_price(product) or 0)
        except Exception:
            bid = 1.0
    # cross the spread slightly for fill on limit-only books
    return max(bid * 0.999, bid - 0.001) if bid > 0 else 0.999


def _aggressive_ask(ex: Any, product: str) -> float:
    book = {}
    try:
        book = ex.get_best_bid_ask(product) or {}
    except Exception:
        book = {}
    ask = float(book.get("ask") or book.get("last") or 0)
    if ask <= 0:
        try:
            ask = float(ex.get_price(product) or 0)
        except Exception:
            ask = 1.0
    return ask * 1.001 if ask > 0 else 1.001


def _sell_usdt_for_usdc(ex: Any, usdt_size: float) -> Dict[str, Any]:
    """USDT → USDC. USDT-USDC is limit-only on this venue."""
    size = float(usdt_size)
    if size < MIN_HOP_USD:
        return {"success": False, "error": "usdt_size_too_small", "size": size}

    if _limit_only(ex, USDT_USDC) and hasattr(ex, "place_limit_sell"):
        px = _aggressive_bid(ex, USDT_USDC)
        return ex.place_limit_sell(USDT_USDC, size, px, post_only=False)

    # try market first; on limit-only error fall back to limit
    sell = ex.place_market_sell(USDT_USDC, size)
    if _ok_order(sell):
        return sell
    err = str((sell or {}).get("error") or sell)
    if "limit only" in err.lower() and hasattr(ex, "place_limit_sell"):
        px = _aggressive_bid(ex, USDT_USDC)
        return ex.place_limit_sell(USDT_USDC, size, px, post_only=False)
    return sell if isinstance(sell, dict) else {"success": False, "error": str(sell)}


def _buy_usdt_with_usdc(ex: Any, usdc_amount: float) -> Dict[str, Any]:
    """USDC → USDT via USDT-USDC (quote USDC). Limit-only book → aggressive ask limit buy."""
    amt = float(usdc_amount)
    if amt < MIN_HOP_USD:
        return {"success": False, "error": "usdc_amount_too_small"}

    if _limit_only(ex, USDT_USDC) and hasattr(ex, "place_limit_buy"):
        px = _aggressive_ask(ex, USDT_USDC)
        # base size ≈ quote/price for ~1:1 stables
        base = amt / max(px, 1e-9)
        return ex.place_limit_buy(USDT_USDC, base, px, post_only=False)

    buy = ex.place_market_buy(USDT_USDC, amt)
    if _ok_order(buy):
        return buy
    err = str((buy or {}).get("error") or buy)
    if "limit only" in err.lower() and hasattr(ex, "place_limit_buy"):
        px = _aggressive_ask(ex, USDT_USDC)
        base = amt / max(px, 1e-9)
        return ex.place_limit_buy(USDT_USDC, base, px, post_only=False)
    return buy if isinstance(buy, dict) else {"success": False, "error": str(buy)}


def _usdt_hop_usd_to_usdc(ex: Any, usd_amount: float) -> Dict[str, Any]:
    usd_amount = float(usd_amount)
    before_usdt = _bal(ex, "USDT")
    before_usdc = _bal(ex, "USDC")
    before_usd = _bal(ex, "USD")

    buy = ex.place_market_buy(USDT_USD, usd_amount)
    if not _ok_order(buy):
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usd_to_usdc",
            "stage": "buy_usdt_usd",
            "error": buy,
            "snap_before": {"usd": before_usd, "usdt": before_usdt, "usdc": before_usdc},
        }

    after_buy_usdt = _wait_bal(ex, "USDT", usd_amount * 0.9, before_usdt)
    usdt_got = max(0.0, after_buy_usdt - before_usdt)
    if usdt_got < MIN_HOP_USD:
        # filled_size may lag; use full USDT wallet if it looks like our fill
        if after_buy_usdt >= MIN_HOP_USD:
            usdt_got = after_buy_usdt
        else:
            usdt_got = max(usdt_got, usd_amount * 0.995)

    sell_size = max(0.0, float(f"{usdt_got:.2f}"))
    if sell_size < MIN_HOP_USD:
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usd_to_usdc",
            "stage": "no_usdt_after_buy",
            "buy": buy,
            "usdt_bal": after_buy_usdt,
            "usdt_delta": after_buy_usdt - before_usdt,
        }

    sell = _sell_usdt_for_usdc(ex, sell_size)
    if not _ok_order(sell):
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usd_to_usdc",
            "stage": "sell_usdt_usdc",
            "error": sell,
            "buy": buy,
            "usdt_sold_attempt": sell_size,
        }

    after_usdc = _wait_bal(ex, "USDC", sell_size * 0.9, before_usdc)
    after = {
        "usd": _bal(ex, "USD"),
        "usdt": _bal(ex, "USDT"),
        "usdc": after_usdc,
    }
    usdc_delta = after["usdc"] - before_usdc
    ok = usdc_delta >= MIN_HOP_USD or after["usdt"] < MIN_HOP_USD
    return {
        "success": bool(ok),
        "method": "usdt_hop",
        "direction": "usd_to_usdc",
        "requested_usd": usd_amount,
        "usdt_sold": sell_size,
        "buy": buy,
        "sell": sell,
        "snap_before": {"usd": before_usd, "usdt": before_usdt, "usdc": before_usdc},
        "snap_after": after,
        "usdc_delta": usdc_delta,
        "usd_delta": after["usd"] - before_usd,
        "error": None if ok else "usdc_balance_did_not_rise",
    }


def _usdt_hop_usdc_to_usd(ex: Any, usdc_amount: float) -> Dict[str, Any]:
    usdc_amount = float(usdc_amount)
    before_usdt = _bal(ex, "USDT")
    before_usdc = _bal(ex, "USDC")
    before_usd = _bal(ex, "USD")

    buy = _buy_usdt_with_usdc(ex, usdc_amount)
    if not _ok_order(buy):
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usdc_to_usd",
            "stage": "buy_usdt_usdc",
            "error": buy,
            "snap_before": {"usd": before_usd, "usdt": before_usdt, "usdc": before_usdc},
        }

    after_buy_usdt = _wait_bal(ex, "USDT", usdc_amount * 0.9, before_usdt)
    usdt_got = max(0.0, after_buy_usdt - before_usdt)
    if usdt_got < MIN_HOP_USD:
        if after_buy_usdt >= MIN_HOP_USD:
            usdt_got = after_buy_usdt
        else:
            usdt_got = max(usdt_got, usdc_amount * 0.995)

    sell_size = max(0.0, float(f"{usdt_got:.2f}"))
    if sell_size < MIN_HOP_USD:
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usdc_to_usd",
            "stage": "no_usdt_after_buy",
            "buy": buy,
            "usdt_bal": after_buy_usdt,
        }

    sell = ex.place_market_sell(USDT_USD, sell_size)
    if not _ok_order(sell):
        return {
            "success": False,
            "method": "usdt_hop",
            "direction": "usdc_to_usd",
            "stage": "sell_usdt_usd",
            "error": sell,
            "buy": buy,
            "usdt_sold_attempt": sell_size,
        }

    after_usd = _wait_bal(ex, "USD", sell_size * 0.9, before_usd)
    after = {
        "usd": after_usd,
        "usdt": _bal(ex, "USDT"),
        "usdc": _bal(ex, "USDC"),
    }
    usd_delta = after["usd"] - before_usd
    ok = usd_delta >= MIN_HOP_USD or after["usdt"] < MIN_HOP_USD
    return {
        "success": bool(ok),
        "method": "usdt_hop",
        "direction": "usdc_to_usd",
        "requested_usdc": usdc_amount,
        "usdt_sold": sell_size,
        "buy": buy,
        "sell": sell,
        "snap_before": {"usd": before_usd, "usdt": before_usdt, "usdc": before_usdc},
        "snap_after": after,
        "usdc_delta": after["usdc"] - before_usdc,
        "usd_delta": usd_delta,
        "error": None if ok else "usd_balance_did_not_rise",
    }


def convert_usd_to_usdc(ex: Any, usd_amount: float) -> Dict[str, Any]:
    """Convert USD → USDC. Native convert first, else USDT hop."""
    usd_amount = float(usd_amount)
    if usd_amount < MIN_HOP_USD:
        return {"success": False, "error": "amount_too_small"}

    native = try_native_convert(ex, from_ccy="USD", to_ccy="USDC", amount=usd_amount)
    if native.get("success"):
        logger.info("[USDC-CONVERT] native USD→USDC $%.2f ok", usd_amount)
        return native
    logger.info(
        "[USDC-CONVERT] native USD→USDC unavailable (%s) — USDT hop $%.2f",
        (native.get("error") or "")[:120],
        usd_amount,
    )
    hop = _usdt_hop_usd_to_usdc(ex, usd_amount)
    hop["native_attempt"] = {k: native.get(k) for k in ("success", "error", "stage")}
    if hop.get("success"):
        logger.info(
            "[USDC-CONVERT] USDT hop USD→USDC ok req=$%.2f usdc_delta=%.2f",
            usd_amount,
            hop.get("usdc_delta") or 0,
        )
    else:
        logger.error("[USDC-CONVERT] USD→USDC failed: %s", hop.get("stage") or hop.get("error"))
    return hop


def convert_usdc_to_usd(ex: Any, usdc_amount: float) -> Dict[str, Any]:
    """Convert USDC → USD. Native convert first, else USDT hop."""
    usdc_amount = float(usdc_amount)
    if usdc_amount < MIN_HOP_USD:
        return {"success": False, "error": "amount_too_small"}

    native = try_native_convert(ex, from_ccy="USDC", to_ccy="USD", amount=usdc_amount)
    if native.get("success"):
        logger.info("[USDC-CONVERT] native USDC→USD $%.2f ok", usdc_amount)
        return native
    logger.info(
        "[USDC-CONVERT] native USDC→USD unavailable (%s) — USDT hop $%.2f",
        (native.get("error") or "")[:120],
        usdc_amount,
    )
    hop = _usdt_hop_usdc_to_usd(ex, usdc_amount)
    hop["native_attempt"] = {k: native.get(k) for k in ("success", "error", "stage")}
    if hop.get("success"):
        logger.info(
            "[USDC-CONVERT] USDT hop USDC→USD ok req=$%.2f usd_delta=%.2f",
            usdc_amount,
            hop.get("usd_delta") or 0,
        )
    else:
        logger.error("[USDC-CONVERT] USDC→USD failed: %s", hop.get("stage") or hop.get("error"))
    return hop


def convert_via_runner(
    runner: Any,
    *,
    direction: str,
    amount: float,
) -> Dict[str, Any]:
    """
    direction: 'usd_to_usdc' | 'usdc_to_usd'
    """
    ex = _exchange_from_runner(runner)
    if ex is None:
        return {"success": False, "error": "no_exchange_on_runner"}

    # Shadow / non-live: intent only
    mode = str(getattr(runner, "mode", "") or "").lower()
    if mode != "live" or getattr(ex, "shadow_mode", False):
        return {
            "success": True,
            "shadow": True,
            "direction": direction,
            "amount": float(amount),
            "method": "shadow_intent",
        }

    if direction == "usd_to_usdc":
        return convert_usd_to_usdc(ex, amount)
    if direction == "usdc_to_usd":
        return convert_usdc_to_usd(ex, amount)
    return {"success": False, "error": f"bad_direction:{direction}"}
