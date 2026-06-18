from exchange_client import CoinbaseExchangeClient
from stop_loss_manager import StopLossManager
import math

class MockConfig:
    def get(self, key, default):
        if key == "risk_management":
            return {"stop_loss_pct": 0.03, "take_profit_pct": 0.06}
        return {}

def test_quantization():
    exchange = CoinbaseExchangeClient(mode="shadow")
    config = MockConfig()
    sl_manager = StopLossManager(exchange, config)

    test_cases = [
        {"pair": "BTC-USD", "entry": 65000.0, "expected_stop_base": 65000.0 * 0.97},
        {"pair": "DOGE-USD", "entry": 0.12, "expected_stop_base": 0.12 * 0.97},
        {"pair": "XRP-USD", "entry": 0.50, "expected_stop_base": 0.50 * 0.97},
    ]

    for tc in test_cases:
        pair = tc["pair"]
        entry = tc["entry"]
        meta = exchange.get_product_metadata(pair)
        
        # Test stop_price rounding
        stop_raw = entry * 0.97
        q_stop = exchange.round_to_increment(stop_raw, meta["price_increment"])
        
        print(f"Pair: {pair}")
        print(f"  Entry: {entry}")
        print(f"  Raw SL: {stop_raw}")
        print(f"  Quantized SL: {q_stop}")
        print(f"  Increment: {meta['price_increment']}")
        
        # Verify stop < entry
        assert q_stop < entry, f"Stop {q_stop} >= entry {entry} for {pair}"
        # Verify quantization
        assert q_stop % meta["price_increment"] < 1e-9, f"Stop {q_stop} not multiple of {meta['price_increment']}"

    print("All isolation tests passed!")

if __name__ == "__main__":
    test_quantization()
