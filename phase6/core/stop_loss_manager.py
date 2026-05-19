"""
Stop Loss Manager for Phase 6

Handles stop-loss placement at the Coinbase level using native orders.
This is mandatory before going live.
"""

from typing import Optional, Any
import uuid


class StopLossManager:
    """
    Manage stop-loss orders for Phase 6 using native Coinbase stop-limit orders.

    Recommended approach (from PHASE_6_NATIVE_SL_SPEC.md):
    - Use stop_limit_stop_limit_gtc orders
    - Fixed 3% or ATR-based stop
    """

    def __init__(self, exchange_client: Any, config: dict, mode: str = "shadow"):
        self.exchange = exchange_client
        self.config = config
        self.mode = mode
        self.shadow_mode = (mode == "shadow")

        # Default risk parameters (can be overridden by config)
        self.default_sl_pct = config.get("risk_management", {}).get("stop_loss_pct", 0.03)

    def attach_stop_loss(self, pair: str, entry_price: float, size: float = None) -> bool:
        """
        Attach a stop loss to a newly opened position.

        Args:
            pair: Trading pair (e.g. "BTC-USD")
            entry_price: Price at which the position was entered
            size: Position size in base currency (optional for now)

        Returns:
            True if stop loss was successfully attached (or logged in shadow)
        """
        stop_price = round(entry_price * (1 - self.default_sl_pct), 2)
        limit_price = round(stop_price * 0.995, 2)  # 0.5% buffer

        if self.shadow_mode:
            print(f"[SHADOW] Would attach native SL for {pair}")
            print(f"         Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f} | Limit: ${limit_price:.2f}")
            return True

        # Live mode - place native stop-limit order
        try:
            success = self.exchange.place_stop_limit_sell(
                product_id=pair,
                qty=size or 0.001,  # placeholder size
                stop_price=stop_price,
                limit_price=limit_price
            )
            if success:
                print(f"[LIVE] Native stop-limit SL placed for {pair} @ ${stop_price}")
            return success
        except Exception as e:
            print(f"[ERROR] Failed to place native SL for {pair}: {e}")
            return False

    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> bool:
        """
        Lower-level method to place a native stop-limit sell order.
        Delegates to the exchange client.
        """
        if self.shadow_mode:
            print(f"[SHADOW] place_stop_limit_sell {product_id} @ stop=${stop_price}")
            return True

        # In real implementation, this would call the exchange client's method
        # For now we delegate
        if hasattr(self.exchange, "place_stop_limit_sell"):
            return self.exchange.place_stop_limit_sell(
                product_id=product_id,
                qty=qty,
                stop_price=stop_price,
                limit_price=limit_price
            )

        print(f"[TODO] Real native stop-limit order not yet wired for {product_id}")
        return False
