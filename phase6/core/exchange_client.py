"""
Stub for CoinbaseExchangeClient (Phase 6)

Allows the runner to initialize and run in shadow mode.
Real implementation should replace this before live trading.
"""

class CoinbaseExchangeClient:
    def __init__(self, mode: str = "shadow"):
        self.mode = mode
        self.shadow_mode = (mode == "shadow")

    def get_account_balance(self, currency: str = "USD"):
        return 1000.0 if self.shadow_mode else 0.0

    def get_prices(self, pairs):
        return {p: 50000.0 for p in pairs} if self.shadow_mode else {}

    def place_market_buy(self, pair, amount_usd):
        print(f"[STUB] Would buy ${amount_usd} of {pair}")
        return type("obj", (object,), {"success": True, "order_id": "stub"})()

    def get_price(self, pair):
        return 50000.0

    def place_stop_limit_sell(self, product_id: str, qty: float,
                              stop_price: float, limit_price: float = None):
        """Stub for native stop-limit order"""
        if self.shadow_mode:
            print(f"[SHADOW] place_stop_limit_sell {product_id} | stop=${stop_price}")
            return True
        print(f"[TODO] Real stop-limit order for {product_id}")
        return False
