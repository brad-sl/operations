#!/usr/bin/env python3
"""
Advanced Price Wrapper for Cryptocurrency Trading Bot
Supports multiple price sources with robust error handling and logging
"""

import logging
import requests
import json
from typing import Union, Dict, Any, List
import os
import time
from dotenv import load_dotenv

class PublicExchangePriceWrapper:
    def __init__(self, backup_sources=None):
        """
        Initialize price wrapper with multiple fallback sources and advanced error handling
        """
        load_dotenv()
        self.logger = logging.getLogger(__name__)
        
        # Coinbase API configuration
        self.coinbase_api_base = "https://api.pro.coinbase.com/products"
        
        # Backup sources (in order of preference)
        self.backup_sources = backup_sources or [
            "https://api.coingecko.com/api/v3/simple/price",
            "https://api.binance.com/api/v3/ticker/price"
        ]
        
        # API Keys and Tokens
        self.coinbase_api_key = os.getenv('COINBASE_API_KEY')
        self.coinbase_api_secret = os.getenv('COINBASE_API_SECRET')
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = None
    
    def _log_error(self, pair: str, source: str, error: Exception):
        """
        Advanced error logging and tracking
        """
        self.error_count += 1
        self.last_error_time = time.time()
        
        # Log detailed error information
        self.logger.error(
            f"Price Fetch Error: "
            f"Pair={pair}, "
            f"Source={source}, "
            f"Error={str(error)}, "
            f"Error Count={self.error_count}"
        )
        
        # Optional: Implement circuit breaker logic
        if self.error_count > 10:
            self.logger.critical("Excessive price fetch errors. Potential systemic issue.")
    
    def _fetch_coinbase_price(self, pair: str) -> Union[float, None]:
        """
        Fetch price from Coinbase Pro API with enhanced error handling
        """
        try:
            response = requests.get(
                f"{self.coinbase_api_base}/{pair}/ticker",
                timeout=5  # 5-second timeout
            )
            response.raise_for_status()
            data = response.json()
            price = float(data.get('price', 0))
            
            # Validate price range to prevent erroneous values
            if not (0 < price < 1_000_000):
                raise ValueError(f"Unreasonable price: {price}")
            
            return price
        except Exception as e:
            self._log_error(pair, "Coinbase Pro API", e)
            return None
    
    def _fetch_backup_source(self, pair: str) -> Union[float, None]:
        """
        Fetch price from backup sources with comprehensive error handling
        """
        pair_base = pair.split('-')[0]
        
        # CoinGecko
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    'ids': self._map_to_coingecko(pair_base),
                    'vs_currencies': 'usd'
                },
                timeout=5  # 5-second timeout
            )
            response.raise_for_status()
            data = response.json()
            coingecko_id = self._map_to_coingecko(pair_base)
            price = float(data.get(coingecko_id, {}).get('usd', 0))
            
            # Validate price range
            if not (0 < price < 1_000_000):
                raise ValueError(f"Unreasonable price: {price}")
            
            return price
        except Exception as e:
            self._log_error(pair, "CoinGecko API", e)
            return None
    
    def _fetch_coingecko_batch(self, pairs: list) -> Union[Dict[str, float], None]:
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
                )
                response.raise_for_status()
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
        return None
    
    def _fetch_binance_batch(self, pairs: list) -> Union[Dict[str, float], None]:
        """
        Fallback: Fetch prices from Binance public API (no auth needed).
        Uses individual requests since Binance doesn't batch well.
        """
        try:
            prices = {}
            for pair in pairs:
                try:
                    pair_base = pair.split('-')[0]
                    symbol = pair_base + 'USDT'  # Binance uses USDT pairs
                    
                    response = requests.get(
                        f"https://api.binance.com/api/v3/ticker/price",
                        params={'symbol': symbol},
                        timeout=5
                    )
                    response.raise_for_status()
                    data = response.json()
                    price = float(data.get('price', 0))
                    
                    if 0 < price < 1_000_000:
                        prices[pair] = price
                    else:
                        prices[pair] = 0.0
                except Exception as inner_e:
                    self.logger.debug(f"Binance fetch failed for {pair}: {inner_e}")
                    prices[pair] = 0.0
            
            successful = len([p for p in prices.values() if p > 0])
            if successful > 0:
                self.logger.info(f"✅ Binance fallback: {successful}/{len(pairs)} prices")
                return prices
            else:
                self.logger.warning(f"Binance batch fetch: 0/{len(pairs)} successful")
                return None
        except Exception as e:
            self.logger.error(f"Binance batch fetch failed: {e}")
            return None
    
    def _map_to_coingecko(self, symbol: str) -> str:
        """
        Map cryptocurrency symbols to CoinGecko IDs
        """
        mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'XRP': 'ripple',
            'DOGE': 'dogecoin',
            'ADA': 'cardano',
            'SOL': 'solana'
        }
        return mapping.get(symbol, symbol.lower())
    
    def get_price(self, pair: str) -> float:
        """
        Get cryptocurrency price with multiple fallback mechanisms
        and comprehensive error handling
        """
        # Attempt Coinbase first
        price = self._fetch_coinbase_price(pair)
        
        # If Coinbase fails, try backup sources
        if price is None or price == 0:
            price = self._fetch_backup_source(pair)
        
        # Hardcoded fallback prices (for absolute last resort)
        fallback_prices = {
            'BTC-USD': 72000,
            'XRP-USD': 1.50,
            'ETH-USD': 3800,
            'DOGE-USD': 0.20,
            'ADA-USD': 1.10,
            'SOL-USD': 180
        }
        
        if price is None or price == 0:
            price = fallback_prices.get(pair, 100)
            self.logger.warning(f"Using hardcoded fallback price for {pair}: ${price}")
        
        return float(price)
    
    def get_prices_batch(self, pairs: list) -> Dict[str, float]:
        """
        EFFICIENT: Fetch prices for multiple pairs in single batch request.
        Uses CoinGecko (1 request for all), fallback to Binance, then hardcoded.
        
        Args:
            pairs: List of pair strings (e.g., ['BTC-USD', 'ETH-USD', ...])
        
        Returns:
            Dict mapping each pair to its price (always returns all pairs)
        """
        result = {}
        
        # Try CoinGecko batch (1 request for all pairs)
        prices = self._fetch_coingecko_batch(pairs)
        if prices:
            result.update(prices)
        
        # If any pairs still missing, try Binance batch
        missing_pairs = [p for p in pairs if p not in result or result[p] == 0]
        if missing_pairs:
            self.logger.info(f"Attempting Binance fallback for {len(missing_pairs)} missing pairs")
            binance_prices = self._fetch_binance_batch(missing_pairs)
            if binance_prices:
                result.update(binance_prices)
        
        # For any still-missing prices, use hardcoded fallback
        fallback_prices = {
            'BTC-USD': 72000,
            'XRP-USD': 1.50,
            'ETH-USD': 3800,
            'DOGE-USD': 0.20,
            'ADA-USD': 1.10,
            'SOL-USD': 180
        }
        
        for pair in pairs:
            if pair not in result or result[pair] == 0:
                fallback = fallback_prices.get(pair, 100)
                result[pair] = fallback
                self.logger.warning(f"Using hardcoded fallback for {pair}: ${fallback}")
        
        return result

def setup_logging():
    """Configure logging for the price wrapper"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/logs/price_wrapper.log')
        ]
    )

if __name__ == '__main__':
    setup_logging()
    price_wrapper = PublicExchangePriceWrapper()
    
    # Test price fetching
    test_pairs = ['BTC-USD', 'XRP-USD', 'ETH-USD', 'DOGE-USD']
    for pair in test_pairs:
        print(f"{pair} Price: ${price_wrapper.get_price(pair):.4f}")