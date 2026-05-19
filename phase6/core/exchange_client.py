"""
Phase 6 Exchange Client (Shadow + Live capable)

This module provides a unified interface for both shadow and live trading.
In shadow mode it simulates realistic behavior without placing real orders.
"""

from typing import Dict, Any, Optional
import time


class CoinbaseExchangeClient:
    """
    Unified exchange client for Phase 6.

    - Shadow mode: Simulates balances, prices, and order execution
    - Live mode: Delegates to real Coinbase Advanced Trade client
    """

    def __init__(self, mode: str = "shadow", initial_capital: float = 1000.0):
        self.mode = mode.lower()
        self.shadow_mode = (self.mode == "shadow")
        self._balances = {"USD": initial_capital}
        self._positions: Dict[str, float] = {}
        self._order_log = []

    # ------------------------------------------------------------------
    # Account & Market Data
    # ------------------------------------------------------------------

    def get_account_balance(self, currency: str = "USD") -> float:
        if self.shadow_mode:
            return self._balances.get(currency, 0.0)
        # TODO: Real implementation
        return 0.0

    def get_price(self, product_id: str) -> float:
        if self.shadow_mode:
            # Simple simulated prices
            prices = {
                "BTC-USD": 65000.0,
                "ETH-USD": 3200.0,
                "SOL-USD": 145.0,
                "XRP-USD": 0.52,
                "DOGE-USD": 0.12,
                "ADA-USD": 0.38,
            }
            return prices.get(product_id, 100.0)
        # TODO: Real implementation
        return 0.0

    def get_prices(self, product_ids: list) -> Dict[str, float]:
        return {pid: self.get_price(pid) for pid in product_ids}

    # ------------------------------------------------------------------
    # Order Execution (Shadow + Live)
    # ------------------------------------------------------------------

    def place_market_buy(self, product_id: str, quote_size: float) -> Dict[str, Any]:
        """Market buy using quote currency (USD)"""
        price = self.get_price(product_id)
        base_size = round(quote_size / price, 6)

        if self.shadow_mode:
            self._balances["USD"] = self._balances.get("USD", 0) - quote_size
            self._positions[product_id] = self._positions.get(product_id, 0) + base_size
            self._order_log.append({
                "type": "market_buy",
                "pair": product_id,
                "quote_size": quote_size,
                "base_size": base_size,
                "price": price,
                "timestamp": time.time()
            })
            return {"success": True, "order_id": f"shadow-{int(time.time())}"}

        # TODO: Real implementation
        return {"success": False, "error": "Live not implemented"}

    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> bool:
        """Place native stop-limit sell order"""
        if self.shadow_mode:
            self._order_log.append({
                "type": "stop_limit_sell",
                "pair": product_id,
                "qty": qty,
                "stop_price": stop_price,
                "limit_price": limit_price,
                "timestamp": time.time()
            })
            print(f"[SHADOW] Stop-limit SL placed for {product_id} @ ${stop_price}")
            return True

        # TODO: Real native stop-limit implementation
        print(f"[TODO] Live stop-limit order for {product_id}")
        return False

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_order_log(self):
        return self._order_log

    def reset_shadow_state(self):
        """Reset simulated balances and positions (useful for testing)"""
        self._balances = {"USD": 1000.0}
        self._positions = {}
        self._order_log = []
