#!/usr/bin/env python3
"""
Phase 6 OrderExecutor - Robust Order Execution Wrapper
"""

import logging
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class OrderExecutor:
    """Robust order executor for Phase 6."""

    def __init__(
        self,
        exchange: Any,
        stop_loss_manager: Any,
        mode: str = "shadow",
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.exchange = exchange
        self.stop_loss_manager = stop_loss_manager
        self.mode = mode.lower().strip()
        self.shadow_mode = self.mode == "shadow"
        self.logger = logger or logging.getLogger("phase6.executor")
        self.max_retries = max_retries
        self.base_delay = base_delay

    def _generate_client_order_id(self, prefix: str = "phase6") -> str:
        return f"{prefix}-{secrets.token_hex(16)}"

    def _retry_with_backoff(self, func, *args, **kwargs) -> Dict[str, Any]:
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                time.sleep(self.base_delay * (2 ** (attempt - 1)))
        return {"success": False, "error": str(last_error)}

    def execute_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        if self.shadow_mode:
            # Simulate fill using current price so SL attachment can be exercised in shadow
            entry_price = getattr(self.exchange, 'get_price', lambda p: 0.0)(pair) or 0.0
            size = usd_amount / entry_price if entry_price > 0 else 0.0
            sl_result = False
            if self.stop_loss_manager:
                sl_result = self.stop_loss_manager.attach_stop_loss(pair, entry_price, size)
            return {
                "success": True,
                "order_id": "shadow_buy",
                "entry_price": round(entry_price, 4),
                "size": round(size, 6),
                "sl_attached": sl_result
            }

        def _do_buy():
            return self.exchange.place_market_buy(pair, usd_amount)

        result = self._retry_with_backoff(_do_buy)

        if result.get("success"):
            # Post-fill: approximate entry with current price (production should query fill details)
            entry_price = getattr(self.exchange, 'get_price', lambda p: 0.0)(pair) or (usd_amount / 1.0)
            size = usd_amount / entry_price if entry_price > 0 else 0.0

            sl_result = False
            if self.stop_loss_manager:
                # Live needs a short settlement window before the asset is available for stop sell order
                if getattr(self, "mode", None) == "live":
                    import time
                    self.logger.info("[SL] Waiting 8s for buy settlement before attaching stop...")
                    time.sleep(8)
                sl_result = self.stop_loss_manager.attach_stop_loss(pair, entry_price, size)
                self.logger.info(f"[SL] Post-buy attach attempt for {pair}: entry=${entry_price:.4f} size={size:.6f} result={sl_result}")
            result["entry_price"] = round(entry_price, 4)
            result["size"] = round(size, 6)
            result["sl_attached"] = sl_result
        else:
            result["sl_attached"] = False

        return result

    def execute_sell(self, pair: str, size: float) -> Dict[str, Any]:
        """Execute a market sell."""
        if self.mode == "live":
            result = self.exchange.place_market_sell(pair, size)
            if not result.get("success", False):
                return {"success": False, "error": result.get("error", "Failed")}
            return {"success": True, "order_id": result.get("order_id") or result.get("id")}
        
        # Shadow mode
        return {"success": True, "order_id": f"shadow_sell-{secrets.token_hex(4)}"}

    def execute_rebalance_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full rebalance plan.
        Processes SELL moves first, and aborts if a SELL fails in live mode.
        """
        results = []
        sorted_plan = sorted(plan, key=lambda x: x.get("action", "") != "SELL")

        for move in sorted_plan:
            pair = move.get("pair")
            action = move.get("action", "").upper()
            usd_amount = float(move.get("usd_amount", 0))

            if action == "BUY":
                result = self.execute_buy(pair, usd_amount)
                # Note: execute_buy now handles SL attachment internally (including shadow simulation)
            elif action == "SELL":
                result = self.execute_sell(pair, usd_amount)
            else:
                result = {"success": False, "error": f"unknown action: {action}"}

            result["pair"] = pair
            result["action"] = action
            results.append(result)
            
            # Atomic enforcement: abort plan if SELL failed in live mode
            if self.mode == "live" and action == "SELL" and not result.get("success"):
                self.logger.error(f"[ATOMIC] SELL failed ({pair}). Aborting full plan execution.")
                break

        return results
