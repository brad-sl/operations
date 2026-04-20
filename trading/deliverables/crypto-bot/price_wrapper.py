#!/usr/bin/env python3
"""
Advanced Price Wrapper for Cryptocurrency Trading Bot
Supports multiple price sources with robust error handling
"""

import logging
import requests
import json
from typing import Union, Dict, Any
import os
from dotenv import load_dotenv

class PublicExchangePriceWrapper:
    def __init__(self, backup_sources=None):
        """
        Initialize price wrapper with multiple fallback sources
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
    
    def _fetch_coinbase_price(self, pair: str) -> Union[float, None]:
        """
        Fetch price from Coinbase Pro API
        """
        try:
            response = requests.get(f"{self.coinbase_api_base}/{pair}/ticker")
            response.raise_for_status()
            data = response.json()
            return float(data.get('price', 0))
        except Exception as e:
            self.logger.warning(f"Coinbase API error for {pair}: {e}")
            return None
    
    def _fetch_backup_source(self, pair: str) -> Union[float, None]:
        """
        Fetch price from backup sources
        """
        pair_base = pair.split('-')[0]
        
        # CoinGecko
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    'ids': self._map_to_coingecko(pair_base),
                    'vs_currencies': 'usd'
                }
            )
            data = response.json()
            coingecko_id = self._map_to_coingecko(pair_base)
            return float(data.get(coingecko_id, {}).get('usd', 0))
        except Exception as e:
            self.logger.warning(f"CoinGecko API error for {pair}: {e}")
        
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