"""
Stop Loss Manager for Phase 6

Handles stop-loss placement at the Coinbase level (native orders preferred).
This module is mandatory before going live.

Current status: Partial implementation. attach_stop_loss() is stubbed.
Full native stop_limit order placement should be completed before live trading.
"""

from typing import Optional, Any


class StopLossManager:
    """
    Manage stop-loss orders for Phase 6.

    Designed to work with Coinbase Advanced Trade API for native SL orders.
    """

    def __init__(self, exchange_client: Any, config: dict, mode: str = "shadow"):
        """
        Args:
            exchange_client: An exchange client instance (e.g. CoinbaseExchangeClient)
            config: Configuration dictionary
            mode: "shadow" or "live"
        """
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.shadow_mode = (mode == "shadow")

    def attach_stop_loss(self, pair: str, entry_price: float) -> bool:
        """
        Attach a stop loss to a newly opened position.

        TODO: Implement native Coinbase stop-limit order here.
        For now this is a stub that logs intent.

        Recommended approach (see PHASE_6_NATIVE_SL_SPEC.md):
        - Use stop_limit_stop_limit_gtc orders
        - Calculate stop_price based on ATR or fixed % (e.g. 2-3%)
        """
        if self.shadow_mode:
            print(f"[SHADOW] Would attach stop loss for {pair} @ entry ${entry_price:.2f}")
            return True

        # Placeholder for real implementation
        # Example:
        # stop_price = entry_price * 0.97
        # limit_price = stop_price * 0.995
        # self.exchange.place_stop_limit_sell(pair, ..., stop_price, limit_price)

        print(f"[TODO] Attach real stop loss for {pair} at Coinbase level")
        return False

    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Lower-level method to place a stop-limit sell order.
        Can be used directly if needed.
        """
        if self.shadow_mode:
            print(f"[SHADOW] Would place stop-limit sell for {product_id}")
            return True, "shadow-order-id", None

        # Real implementation would call the exchange client here
        print(f"[TODO] Implement native stop-limit order for {product_id}")
        return False, None, "Not implemented"