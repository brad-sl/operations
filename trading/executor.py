"""
TradeExecutor — the primary callable module for initiating trades.

Any trading bot (runner, script, strategy) should use this (or a
higher-level strategy) rather than calling the raw client.

Follows BUILD_PHILOSOPHY: thin, injected, observable, real/safe.
"""

from __future__ import annotations

import logging
import secrets
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional

from .client import TradingClient
from .types import TradeResult, AttrDict

try:
    from phase6.core.stop_loss_coordinator import StopLossCoordinator
except Exception:
    StopLossCoordinator = None

logger = logging.getLogger(__name__)

class TradeExecutor:
    """Primary execution boundary for ARCH-4 platform path."""

    def __init__(
        self,
        client: TradingClient,
        stop_loss_coordinator: Optional[Any] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.client = client
        self.stop_loss_coordinator = stop_loss_coordinator
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.logger = logger or logging.getLogger("trading.executor")
        self.shadow_mode = getattr(client, "shadow_mode", getattr(client, "mode", "shadow") == "shadow")

    def _retry(self, func, *args, **kwargs) -> Dict[str, Any]:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                time.sleep(self.base_delay * (2 ** (attempt - 1)))
        return {"success": False, "error": str(last_error)}

    def execute_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        """Execute BUY with recovery logic for insufficient funds etc. Matches decompiled behavior."""
        def _do():
            return self.client.place_market_buy(pair, usd_amount)

        result = self._retry(_do)

        # simulate classified etc
        try:
            from trading.client import classify_preview_or_order_error  # may not exist
        except Exception:
            def classify_preview_or_order_error(err): 
                t = err.get("type") or err.get("preview_failure_reason") or "UNKNOWN"
                return {"type": t, "action": "log_and_continue"}

        classified = None
        try:
            err_resp = {
                "error": getattr(result, "get", lambda k,d: result.get(k,d) if isinstance(result,dict) else getattr(result,k,d)) ("error", ""),
                "preview_failure_reason": "",
            }
            if hasattr(result, "details"):
                err_resp["preview_failure_reason"] = result.get("details", {}).get("preview_failure_reason", "")
            classified = classify_preview_or_order_error(err_resp)
        except Exception:
            classified = {"type": "UNKNOWN", "action": "log_and_continue"}

        if not isinstance(result, dict):
            result = dict(result) if hasattr(result, "keys") else {"success": False}

        result = AttrDict(result) if not isinstance(result, AttrDict) else result
        result["classified"] = classified or result.get("classified")

        original_usd = usd_amount
        if not result.get("success") and isinstance(classified, dict):
            ctype = classified.get("type")
            if ctype in ("INSUFFICIENT_FUND", "PREVIEW_FAILURE"):
                try:
                    avail = self.client.get_account_balance("USD") or 0.0
                    reduced = min(original_usd * 0.8, avail * 0.95)
                    if reduced >= 5.0:
                        self.logger.info(f"[EXECUTOR RECOVERY] Classified {ctype}, retrying BUY {pair} reduced from ${original_usd:.2f} to ${reduced:.2f} (avail=${avail:.2f})")
                        retry_res = self.client.place_market_buy(pair, reduced)
                        if retry_res.get("success"):
                            result = AttrDict(retry_res)
                            result["usd_amount"] = reduced
                            result["recovery_suggestion"] = {"action": "reduced_size", "reduced_usd": reduced, "retried": True, "original_usd": original_usd}
                            usd_amount = reduced  # update for size calc
                        else:
                            result["recovery_suggestion"] = {"action": "defer", "reduced_usd": reduced, "reason": "insufficient even after 80% reduction", "retried": True}
                    else:
                        result["recovery_suggestion"] = {"action": "defer", "reason": "reduced amount below min threshold", "reduced_usd": reduced}
                except Exception as re:
                    self.logger.warning(f"[EXECUTOR RECOVERY] Balance/retry compute failed: {re}")
                    result["recovery_suggestion"] = {"action": "defer", "reason": str(re)}

        if result.get("success"):
            # compute size , attach SL via coordinator
            price = self.client.get_price(pair) or 0.0
            if price <= 0:
                # try from result
                price = float(result.get("entry_price") or result.get("price") or 0.0)
            size = float(result.get("size") or result.get("qty") or (usd_amount / price if price > 0 else 0.0))
            # attach SL
            sl_ok = False
            if self.stop_loss_coordinator and hasattr(self.stop_loss_coordinator, "attach_stop_loss"):
                try:
                    sl_ok = self.stop_loss_coordinator.attach_stop_loss(pair, price, size)
                except Exception as sle:
                    self.logger.warning(f"SL attach failed for {pair}: {sle}")
                    sl_ok = False
            elif self.stop_loss_coordinator and hasattr(self.stop_loss_coordinator, "sl_manager"):
                try:
                    sl_ok = self.stop_loss_coordinator.sl_manager.attach_stop_loss(pair, price, size, order_id=result.get("order_id", "platform"))
                except Exception:
                    sl_ok = False
            result["sl_attached"] = bool(sl_ok)
            result["pair"] = pair
            result["action"] = "BUY"
            result["usd_amount"] = usd_amount
            result["size"] = size
            result["qty"] = size
            if not result.get("entry_price"):
                result["entry_price"] = round(price, 4)
        else:
            result["sl_attached"] = False

        if not result.get("classified"):
            result["classified"] = classified
        return dict(result)  # return plain for compat

    def execute_sell(self, pair: str, size: float) -> Dict[str, Any]:
        def _do():
            return self.client.place_market_sell(pair, size)

        result = self._retry(_do)
        if not isinstance(result, dict):
            result = dict(result) if result else {"success": False}
        result = AttrDict(result)
        result["pair"] = pair
        result["action"] = "SELL"
        result["size"] = size
        result["qty"] = size
        return dict(result)

    def execute_rebalance_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a rebalance plan (list of action dicts with pair, action, usd_amount or size).
        Sorts sells first (as in decompile lambda != SELL first? wait opposite for atomic).
        Uses Decimal quantize.
        Stops on failed SELL in live.
        """
        results: List[Dict[str, Any]] = []
        if not plan:
            return results

        # sort: sells first for safety? decompile sorted by action != 'SELL' so non-sells first? but comment said sorted sells first in practice.
        # follow decompile: sorted(..., key= lambda x: x.get('action','') != 'SELL' )  => sells (==SELL -> False=0) come first
        try:
            sorted_plan = sorted(plan, key=lambda x: str(x.get("action", "")).upper() != "SELL")
        except Exception:
            sorted_plan = list(plan)

        for move in sorted_plan:
            pair = move.get("pair")
            action = str(move.get("action", "")).upper()
            usd = float(move.get("usd_amount", move.get("usd", 0.0)))
            size = float(move.get("size", 0.0))

            # compute raw_size for sell if needed
            raw_size = size
            if action == "SELL" and not raw_size and usd:
                try:
                    price = self.client.get_price(pair) or 1.0
                    raw_size = usd / price
                except Exception:
                    raw_size = 0.0

            # quantize
            try:
                from decimal import Decimal, ROUND_DOWN
                d = Decimal(str(raw_size if raw_size else (usd / (self.client.get_price(pair) or 1))))
                inc = Decimal("0.00000001")
                try:
                    meta = self.client.get_product_metadata(pair)
                    inc = Decimal(str(meta.get("base_increment", "0.00000001")))
                except Exception:
                    pass
                size = float(d.quantize(inc, rounding=ROUND_DOWN))
            except Exception:
                size = round(raw_size or 0.0, 8)

            res = None
            if action == "BUY":
                res = self.execute_buy(pair, usd)
            elif action == "SELL":
                res = self.execute_sell(pair, size)
            else:
                res = TradeResult(success=False, error=f"unknown action: {action}", pair=pair).to_dict()

            # attach attrs for compat
            res = AttrDict(res)
            res["pair"] = pair
            res["action"] = action
            results.append(dict(res))

            # atomic: if live and sell failed, abort remaining
            try:
                if getattr(self.client, "mode", "shadow") == "live" and action == "SELL" and not res.get("success"):
                    self.logger.error(f"[ATOMIC] SELL failed for {pair}. Aborting remaining plan.")
                    break
            except Exception:
                pass

        return results
