import aiohttp
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional
from core.decorators import async_retry
from config.settings import settings
from core.errors import APIError, APITimeout

COINBASE_PRICES_URL = "https://api.coinbase.com/v2/exchange-rates?currency="

class PriceFetcher:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=10)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    @async_retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def fetch_price(self, pair: str) -> Optional[Dict]:
        """Fetch current price for a trading pair (e.g., 'BTC-USD')."""
        try:
            base, quote = pair.split('-')
            async with self.session.get(f"{COINBASE_PRICES_URL}{quote}") as resp:
                if resp.status != 200:
                    raise APIError(f"API error {resp.status}")
                data = await resp.json()
                price = Decimal(data['data']['rates'].get(base, '0'))
                return {
                    'pair': pair,
                    'price': float(price),
                    'timestamp': asyncio.get_event_loop().time()
                }
        except asyncio.TimeoutError:
            raise APITimeout(f"Timeout fetching {pair}")
        except Exception as e:
            raise APIError(f"Error fetching {pair}: {e}")
    
    async def fetch_batch_prices(self, pairs: List[str]) -> Dict[str, Dict]:
        """Batch fetch prices for multiple pairs."""
        tasks = [self.fetch_price(pair) for pair in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        prices = {}
        for pair, result in zip(pairs, results):
            if isinstance(result, dict):
                prices[pair] = result
            else:
                print(f"Failed to fetch {pair}: {result}")
        return prices
