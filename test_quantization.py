
import unittest
from typing import Dict, Any

# Mocking the exchange client for testing
class MockExchangeClient:
    def __init__(self):
        # Realistic product specifications from Coinbase (approximated)
        self.products = {
            "BTC-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "DOGE-USD": {"price_increment": 0.00001, "base_increment": 1.0},
            "XRP-USD": {"price_increment": 0.0001, "base_increment": 0.1},
            "SOL-USD": {"price_increment": 0.001, "base_increment": 0.01},
        }

    def get_product(self, product_id: str):
        return self.products.get(product_id)

    def round_to_increment(self, value: float, increment: float) -> float:
        import math
        # Helper to round correctly to precision
        precision = abs(int(math.log10(increment))) if increment < 1 else 0
        return round(round(value / increment) * increment, precision + 2)

class TestQuantization(unittest.TestCase):
    def setUp(self):
        self.client = MockExchangeClient()

    def test_doge_sl_quantization(self):
        entry_price = 0.12
        sl_pct = 0.03
        product_id = "DOGE-USD"
        
        product = self.client.get_product(product_id)
        stop_price_raw = entry_price * (1 - sl_pct)
        stop_price = self.client.round_to_increment(stop_price_raw, product["price_increment"])
        
        # Original logic was round(entry * (1 - pct), 2) = 0.12 * 0.97 = 0.1164 -> 0.12 again
        # New logic should be 0.1164 rounded to 0.00001 increment -> 0.11640
        self.assertNotEqual(stop_price, entry_price)
        self.assertTrue(stop_price < entry_price)
        print(f"DOGE SL: {entry_price} -> {stop_price} (Increment: {product['price_increment']})")

    def test_xrp_sl_quantization(self):
        entry_price = 0.50
        sl_pct = 0.03
        product_id = "XRP-USD"
        
        product = self.client.get_product(product_id)
        stop_price_raw = entry_price * (1 - sl_pct)
        stop_price = self.client.round_to_increment(stop_price_raw, product["price_increment"])
        
        self.assertNotEqual(stop_price, entry_price)
        self.assertTrue(stop_price < entry_price)
        print(f"XRP SL: {entry_price} -> {stop_price} (Increment: {product['price_increment']})")

if __name__ == "__main__":
    unittest.main()
