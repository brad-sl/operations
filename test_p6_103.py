import sys
import os

# Add project root to path
sys.path.append(os.path.abspath("./projects/crypto-trading-bot"))

from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.stop_loss_manager import StopLossManager

# Mock config
config = {"risk_management": {"stop_loss_pct": 0.03}}

def test_stop_quantization():
    print("--- Running Stop Quantization Isolation Test ---")
    exchange = CoinbaseExchangeClient(mode="shadow")
    sl_manager = StopLossManager(exchange, config, mode="shadow")

    test_cases = [
        {"pair": "DOGE-USD", "entry": 0.12, "size": 100},
        {"pair": "XRP-USD", "entry": 0.50, "size": 50},
        {"pair": "BTC-USD", "entry": 65000.0, "size": 0.1},
        {"pair": "SOL-USD", "entry": 145.0, "size": 10}
    ]

    for tc in test_cases:
        print(f"\nTesting {tc['pair']} (Entry: {tc['entry']})")
        meta = exchange.get_product_metadata(tc['pair'])
        print(f"  Metadata: {meta}")
        
        # Simulate logic from stop_loss_manager.py
        pct = 0.03
        stop_price = exchange.round_to_increment(tc['entry'] * (1 - pct), meta["price_increment"])
        limit_price = exchange.round_to_increment(stop_price * 0.995, meta["price_increment"])
        size = exchange.round_to_increment(tc['size'], meta["base_increment"])
        
        print(f"  Target Stop: {tc['entry'] * (1 - pct):.6f}")
        print(f"  Quantized Stop: {stop_price}")
        print(f"  Quantized Limit: {limit_price}")
        print(f"  Quantized Size: {size}")
        
        # Validation
        if stop_price >= tc['entry']:
            print(f"  ❌ FAILED: Stop price {stop_price} >= entry {tc['entry']}")
        elif limit_price >= stop_price:
            print(f"  ❌ FAILED: Limit price {limit_price} >= stop {stop_price}")
        else:
            print(f"  ✅ PASSED: Stop < Entry, Limit < Stop.")

if __name__ == "__main__":
    test_stop_quantization()
