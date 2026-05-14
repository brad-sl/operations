import re

with open('price_wrapper.py', 'r') as f:
    content = f.read()

# Add imports at top if not present
if 'import time' not in content:
    content = content.replace(
        'import requests',
        'import requests\nimport time'
    )

# Find _fetch_coingecko_batch and add retry logic
old_coingecko = '''    def _fetch_coingecko_batch(self, pairs: list) -> Union[Dict[str, float], None]:
        """
        Fetch prices for multiple pairs in ONE batch request to CoinGecko.
        MUCH more efficient than fetching individually.
        """
        try:
            # Map all pair bases to CoinGecko IDs
            pair_bases = [pair.split('-')[0] for pair in pairs]
            coingecko_ids = [self._map_to_coingecko(base) for base in pair_bases]
            
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    'ids': ','.join(coingecko_ids),  # Comma-separated list
                    'vs_currencies': 'usd'
                },
                timeout=10  # Longer timeout for batch request
            )'''

new_coingecko = '''    def _fetch_coingecko_batch(self, pairs: list) -> Union[Dict[str, float], None]:
        """
        Fetch prices for multiple pairs in ONE batch request to CoinGecko.
        MUCH more efficient than fetching individually.
        Includes exponential backoff for rate limiting.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Map all pair bases to CoinGecko IDs
                pair_bases = [pair.split('-')[0] for pair in pairs]
                coingecko_ids = [self._map_to_coingecko(base) for base in pair_bases]
                
                response = requests.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={
                        'ids': ','.join(coingecko_ids),  # Comma-separated list
                        'vs_currencies': 'usd'
                    },
                    timeout=10  # Longer timeout for batch request
                )'''

content = content.replace(old_coingecko, new_coingecko)

# Add retry wrapper around response handling
old_response = '''            response.raise_for_status()
            data = response.json()
            
            # Map results back to pair format
            prices = {}
            for pair, coingecko_id in zip(pairs, coingecko_ids):
                price = float(data.get(coingecko_id, {}).get('usd', 0))
                
                # Validate price range
                if 0 < price < 1_000_000:
                    prices[pair] = price
                else:
                    self.logger.warning(f"Unreasonable price for {pair}: {price}")
                    prices[pair] = 0.0
            
            self.logger.info(f"✅ CoinGecko batch fetch: {len([p for p in prices.values() if p > 0])}/{len(pairs)} prices")
            return prices
        except Exception as e:
            self.logger.error(f"CoinGecko batch fetch failed: {e}")
            return None'''

new_response = '''                response.raise_for_status()
                data = response.json()
                
                # Map results back to pair format
                prices = {}
                for pair, coingecko_id in zip(pairs, coingecko_ids):
                    price = float(data.get(coingecko_id, {}).get('usd', 0))
                    
                    # Validate price range
                    if 0 < price < 1_000_000:
                        prices[pair] = price
                    else:
                        self.logger.warning(f"Unreasonable price for {pair}: {price}")
                        prices[pair] = 0.0
                
                self.logger.info(f"✅ CoinGecko batch fetch: {len([p for p in prices.values() if p > 0])}/{len(pairs)} prices")
                return prices
            except requests.exceptions.HTTPError as e:
                if '429' in str(e):
                    # Rate limited - exponential backoff
                    wait_time = (2 ** attempt) + 1
                    self.logger.warning(f"CoinGecko 429 rate limit (attempt {attempt+1}/{max_retries}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    self.logger.error(f"CoinGecko batch fetch failed: {e}")
                    return None
            except Exception as e:
                self.logger.error(f"CoinGecko batch fetch failed: {e}")
                return None
        
        self.logger.error(f"CoinGecko batch fetch failed after {max_retries} retries")
        return None'''

content = content.replace(old_response, new_response)

with open('price_wrapper.py', 'w') as f:
    f.write(content)

print("✅ Added exponential backoff for CoinGecko rate limiting")
