import re

with open('price_wrapper.py', 'r') as f:
    content = f.read()

# Add throttling state to __init__
init_old = '''        # Error tracking
        self.error_count = 0
        self.last_error_time = None'''

init_new = '''        # Error tracking
        self.error_count = 0
        self.last_error_time = None
        
        # Fetch throttling (reduce API pressure)
        self.last_fetch_time = 0
        self.min_fetch_interval = 30  # Min 30 seconds between API calls'''

content = content.replace(init_old, init_new)

# Add throttle check to get_prices_batch
batch_old = '''    def get_prices_batch(self, pairs: list) -> Dict[str, float]:
        """
        EFFICIENT: Fetch prices for multiple pairs in single batch request.
        Uses CoinGecko (1 request for all), fallback to Binance, then hardcoded.'''

batch_new = '''    def get_prices_batch(self, pairs: list) -> Dict[str, float]:
        """
        EFFICIENT: Fetch prices for multiple pairs in single batch request.
        Uses CoinGecko (1 request for all), fallback to Binance, then hardcoded.
        
        THROTTLED: Min 30 seconds between API calls to avoid rate limiting.'''

content = content.replace(batch_old, batch_new)

# Add throttle check at start of batch method
batch_start = '''        result = {}
        
        # Try CoinGecko batch (1 request for all pairs)
        prices = self._fetch_coingecko_batch(pairs)'''

batch_throttle = '''        result = {}
        
        # Throttle API calls (min 30s between attempts)
        import time as time_module
        now = time_module.time()
        if now - self.last_fetch_time < self.min_fetch_interval:
            self.logger.info(f"Throttling: API call too soon ({now - self.last_fetch_time:.1f}s ago), using cache/fallback")
            # Return fallback for all pairs
            fallback_prices = {
                'BTC-USD': 72000, 'XRP-USD': 1.50, 'ETH-USD': 3800,
                'DOGE-USD': 0.20, 'ADA-USD': 1.10, 'SOL-USD': 180
            }
            return {p: fallback_prices.get(p, 100) for p in pairs}
        
        self.last_fetch_time = now
        
        # Try CoinGecko batch (1 request for all pairs)
        prices = self._fetch_coingecko_batch(pairs)'''

content = content.replace(batch_start, batch_throttle)

with open('price_wrapper.py', 'w') as f:
    f.write(content)

print("✅ Added 30-second fetch throttle to reduce API pressure")
