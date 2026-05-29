#!/usr/bin/env python3
"""
Phase 6 OrderExecutor - Robust Order Execution Wrapper

Reconciles Phase 5 execution patterns with Phase 6 architecture.
Provides retry logic, client_order_id generation, structured results,
and StopLossManager integration after successful buys.

Usage:
    from .order_executor import OrderExecutor

    executor = OrderExecutor(
        exchange=exchange_client,
        stop_loss_manager=sl_manager,
        mode=mode,
        logger=logger
    )

    result = executor.execute_buy("BTC-USD", 100.0)
"""

import logging
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


class OrderExecutor:
    """
    Robust order executor for Phase 6.

    Features:
    - Exponential backoff retry (3 attempts)
    - Automatic client_order_id generation
    - Structured result dictionaries
    - StopLossManager integration on successful buys
    - Shadow/live mode awareness via exchange client
    """

    def __init__(
        self,
        exchange: Any,
        stop_loss_manager: Any,
        mode: str = "shadow",
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        """
        Initialize OrderExecutor.

        Args:
            exchange: CoinbaseExchangeClient instance
            stop_loss_manager: StopLossManager instance
            mode: "shadow" or "live"
            logger: Optional logger (defaults to phase6.executor)
            max_retries: Maximum retry attempts (default 3)
            base_delay: Base delay in seconds for exponential backoff
        """
        self.exchange = exchange
        self.stop_loss_manager = stop_loss_manager
        self.mode = mode.lower().strip()
        self.shadow_mode = self.mode == "shadow"
        self.logger = logger or logging.getLogger("phase6.executor")
        self.max_retries = max_retries
        self.base_delay = base_delay

        self.logger.info(
            f"OrderExecutor initialized | mode={self.mode} | "
            f"max_retries={max_retries} | base_delay={base_delay}s"
        )

    def _generate_client_order_id(self, prefix: str = "phase6") -> str:
        """Generate a unique client_order_id for traceability."""
        return f"{prefix}-{secrets.token_hex(16)}"

    def _classify_error(self, error: Exception) -> str:
        """Classify error for logging and potential future circuit breaking."""
        err_str = str(error).lower()
        if "rate" in err_str or "429" in err_str:
            return "rate_limit"
        if "timeout" in err_str:
            return "timeout"
        if "insufficient" in err_str or "balance" in err_str:
            return "insufficient_funds"
        if "invalid" in err_str or "bad request" in err_str:
            return "invalid_request"
        return "unknown"

    def _retry_with_backoff(self, func, *args, **kwargs) -> Dict[str, Any]:
        """
        Execute function with exponential backoff retry.

        Returns structured result dict.
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 1:
                    self.logger.info(f"Retry succeeded on attempt {attempt}")
                return result
            except Exception as e:
                last_error = e
                error_type = self._classify_error(e)
                delay = self.base_delay * (2 ** (attempt - 1))

                self.logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed "
                    f"({error_type}): {e}. Retrying in {delay:.1f}s..."
                )

                if attempt < self.max_retries:
                    time.sleep(delay)
                else:
                    self.logger.error(
                        f"All {self.max_retries} attempts failed. "
                        f"Last error: {e}"
                    )

        # All retries exhausted
        return {
            "success": False,
            "order_id": None,
            "client_order_id": None,
            "error": str(last_error),
            "error_type": self._classify_error(last_error) if last_error else "unknown",
            "attempts": self.max_retries,
        }

    def execute_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        """
        Execute a market buy with retry logic and SL attachment.

        Returns structured result:
        {
            "success": bool,
            "order_id": str or None,
            "client_order_id": str or None,
            "price": float or None,
            "size": float or None,
            "sl_attached": bool,
            "error": str or None,
            "timestamp": str
        }
        """
        client_order_id = self._generate_client_order_id()
        timestamp = datetime.utcnow().isoformat()

        self.logger.info(
            f"[BUY] {pair} ${usd_amount:.2f} | client_order_id={client_order_id}"
        )

        if self.shadow_mode:
            self.logger.info(f"[SHADOW] Simulating BUY ${usd_amount:.2f} {pair}")
            price = self.exchange.get_price(pair)
            size = usd_amount / price if price > 0 else 0.0

            # Simulate SL attachment
            sl_attached = self.stop_loss_manager.attach_stop_loss(pair, price, size)

            return {
                "success": True,
                "order_id": f"shadow-{client_order_id}",
                "client_order_id": client_order_id,
                "price": price,
                "size": round(size, 8),
                "sl_attached": sl_attached,
                "error": None,
                "timestamp": timestamp,
            }

        # Live path with retry
        def _do_buy():
            return self.exchange.place_market_buy(pair, usd_amount)

        raw_result = self._retry_with_backoff(_do_buy)

        if not raw_result.get("success", False):
            return {
                "success": False,
                "order_id": None,
                "client_order_id": client_order_id,
                "price": None,
                "size": None,
                "sl_attached": False,
                "error": raw_result.get("error", "Buy failed after retries"),
                "timestamp": timestamp,
            }

        # Success path - fetch price and attach SL
        try:
            price = self.exchange.get_price(pair)
            size = usd_amount / price if price > 0 else 0.0

            sl_attached = self.stop_loss_manager.attach_stop_loss(pair, price, size)

            order_id = raw_result.get("order_id") or raw_result.get("id")

            if sl_attached:
                self.logger.info(
                    f"[SUCCESS] {pair}: bought ${usd_amount:.2f} @ ${price:.2f} | "
                    f"SL attached | order_id={order_id}"
                )
            else:
                self.logger.warning(
                    f"[PARTIAL] {pair}: bought ${usd_amount:.2f} @ ${price:.2f} | "
                    f"SL attachment FAILED"
                )

            return {
                "success": True,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "price": price,
                "size": round(size, 8),
                "sl_attached": sl_attached,
                "error": None,
                "timestamp": timestamp,
            }

        except Exception as e:
            self.logger.exception(f"Post-buy processing error for {pair}: {e}")
            return {
                "success": True,  # Buy succeeded even if post-processing failed
                "order_id": raw_result.get("order_id"),
                "client_order_id": client_order_id,
                "price": None,
                "size": None,
                "sl_attached": False,
                "error": f"Post-buy error: {str(e)}",
                "timestamp": timestamp,
            }

    def execute_sell(self, pair: str, size: float) -> Dict[str, Any]:
        """
        Execute a market sell (stub for Phase 6 - to be fully implemented later).
        """
        self.logger.info(f"[SELL] {pair} size={size} (stub implementation)")
        return {
            "success": True,
            "order_id": f"sell-stub-{secrets.token_hex(8)}",
            "client_order_id": self._generate_client_order_id("sell"),
            "price": None,
            "size": size,
            "error": None,
            "timestamp": datetime.utcnow().isoformat(),
            "note": "SELL execution is stubbed in current Phase 6 scope",
        }

    def execute_rebalance_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full rebalance plan (list of moves).

        Each move should contain: pair, action (BUY/SELL), usd_amount
        Returns list of structured results.
        """
        results = []
        for move in plan:
            pair = move.get("pair")
            action = move.get("action", "").upper()
            usd_amount = float(move.get("usd_amount", 0))

            if not pair or usd_amount < 20:
                results.append(
                    {
                        "success": False,
                        "pair": pair,
                        "action": action,
                        "error": "below minimum or invalid",
                    }
                )
                continue

            if action == "BUY":
                result = self.execute_buy(pair, usd_amount)
            elif action == "SELL":
                # Size approximation for sell stub
                result = self.execute_sell(pair, usd_amount)
            else:
                result = {"success": False, "error": f"unknown action: {action}"}

            result["pair"] = pair
            result["action"] = action
            results.append(result)

        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("✅ OrderExecutor module loaded successfully")