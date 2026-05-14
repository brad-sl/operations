import pytest
from coinbase_wrapper import CoinbaseWrapper, OrderResponse

class TestCoinbaseWrapper:
    """Test suite for Coinbase API wrapper."""
    
    def setup_method(self):
        """Initialize test client."""
        self.wrapper = CoinbaseWrapper(
            api_key="test_key",
            private_key="test_private_key",
            passphrase="test_pass",
            sandbox=True
        )
    
    # Initialization (3 tests)
    def test_init_sandbox_mode(self):
        assert self.wrapper.sandbox is True
        assert "sandbox" in self.wrapper.base_url
    
    def test_init_live_mode(self):
        live = CoinbaseWrapper(
            "key", "private", "pass", sandbox=False
        )
        assert live.sandbox is False
        assert "sandbox" not in live.base_url
    
    def test_init_stores_credentials(self):
        assert self.wrapper.api_key == "test_key"
        assert self.wrapper.private_key == "test_private_key"
    
    # Balance queries (2 tests)
    def test_get_balance_btc(self):
        result = self.wrapper.get_balance("BTC")
        assert result["success"] is True
        assert result["currency"] == "BTC"
        assert result["balance"] == 0.5
    
    def test_get_balance_usd(self):
        result = self.wrapper.get_balance("USD")
        assert result["success"] is True
        assert result["balance"] == 10000.0
    
    # Price queries (2 tests)
    def test_get_price_btc_usd(self):
        result = self.wrapper.get_price("BTC-USD")
        assert result["success"] is True
        assert result["price"] == 50000.0
        assert "change_24h" in result
    
    def test_get_price_structure(self):
        result = self.wrapper.get_price()
        assert "product_id" in result
        assert "change_percent_24h" in result
    
    # Order creation (4 tests)
    def test_create_order_buy_limit(self):
        order = self.wrapper.create_order(
            product_id="BTC-USD",
            side="buy",
            order_type="limit",
            price=50000.0,
            size=0.1
        )
        assert order.success is True
        assert order.side == "buy"
        assert order.price == 50000.0
        assert order.status == "OPEN"
    
    def test_create_order_sell_limit(self):
        order = self.wrapper.create_order(
            product_id="BTC-USD",
            side="sell",
            order_type="limit",
            price=55000.0,
            size=0.05
        )
        assert order.success is True
        assert order.side == "sell"
    
    def test_create_order_invalid_side(self):
        order = self.wrapper.create_order(
            product_id="BTC-USD",
            side="invalid",
            order_type="limit",
            price=50000.0,
            size=0.1
        )
        assert order.success is False
        assert "Invalid side" in order.error
    
    def test_create_order_live_blocked(self):
        live_wrapper = CoinbaseWrapper(
            "key", "private", "pass", sandbox=False
        )
        order = live_wrapper.create_order(
            product_id="BTC-USD",
            side="buy",
            order_type="limit",
            price=50000.0,
            size=0.1
        )
        assert order.success is False
        assert "Live trading requires" in order.error
    
    # Order cancellation (2 tests)
    def test_cancel_order(self):
        order = self.wrapper.cancel_order("order-12345")
        assert order.success is True
        assert order.status == "CANCELLED"
    
    def test_cancel_order_preserves_id(self):
        order = self.wrapper.cancel_order("my-order-id")
        assert order.order_id == "my-order-id"
    
    # Order history (1 test)
    def test_get_orders_returns_list(self):
        orders = self.wrapper.get_orders()
        assert isinstance(orders, list)
    
    # Edge cases (1 test)
    def test_order_response_dataclass(self):
        resp = OrderResponse(
            success=True,
            order_id="test",
            side="buy",
            price=50000.0,
            size=0.1
        )
        assert resp.order_id == "test"
        assert resp.product_id == "BTC-USD"  # default
