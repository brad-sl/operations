"""
Stop Loss Manager for Phase 6

Handles stop-loss (and take-profit) placement at the Coinbase level using native orders.
This is mandatory before going live.
"""

import time
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class StopLossManager:
    """
    Manage stop-loss and take-profit orders for Phase 6 using native Coinbase stop-limit orders.
    """

    def __init__(self, exchange_client: Any, config: dict, mode: str = "shadow"):
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.shadow_mode = (mode == "shadow")

        # Default risk parameters (can be overridden by config)
        self.default_sl_pct = config.get("risk_management", {}).get("stop_loss_pct", 0.03)
        self.default_tp_pct = config.get("risk_management", {}).get("take_profit_pct", 0.06)

    def attach_stop_loss(self, pair: str, entry_price: float, size: float, sl_pct: float = None) -> bool:
        """
        Attach a native stop-loss order with retry logic.

        Returns True on successful placement (or shadow success).
        """
        pct = sl_pct if sl_pct is not None else self.default_sl_pct
        stop_price = round(entry_price * (1 - pct), 2)
        limit_price = round(stop_price * 0.995, 2)

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native SL for {pair}")
            print(f"         Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f} | Limit: ${limit_price:.2f} | SL%: {pct*100:.1f}% | size: {size}")
            return True

        # Live mode with retry
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                result = self.exchange.place_stop_limit_sell(
                    product_id=pair,
                    qty=size,
                    stop_price=stop_price,
                    limit_price=limit_price
                )
                if result:
                    logger.info(f"Stop-loss successfully attached for {pair}")
                    return True
                else:
                    logger.warning(f"SL attempt {attempt}/{max_retries} failed for {pair}")
            except Exception as e:
                logger.error(f"SL attempt {attempt}/{max_retries} exception for {pair}: {e}")

            if attempt < max_retries:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying SL attachment for {pair} in {sleep_time}s...")
                time.sleep(sleep_time)

        logger.error(f"Failed to attach stop-loss for {pair} after {max_retries} attempts")
        return False

    def attach_take_profit(self, pair: str, entry_price: float, size: float, tp_pct: float = None) -> bool:
        """
        Attach a native take-profit limit sell order.
        """
        pct = tp_pct if tp_pct is not None else self.default_tp_pct
        tp_price = round(entry_price * (1 + pct), 2)

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native TP for {pair}")
            print(f"         Entry: ${entry_price:.2f} | TP: ${tp_price:.2f} | TP%: {pct*100:.1f}% | size: {size}")
            return True

        # Use a simple limit sell for TP
        if hasattr(self.exchange, "place_limit_sell"):
            return self.exchange.place_limit_sell(pair, size, tp_price)
        print("[TODO] place_limit_sell not yet implemented on exchange client")
        return False