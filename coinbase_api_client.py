#!/usr/bin/env python3
"""
Coinbase Pro API Client for Cryptocurrency Trading
Supports authentication, price fetching, and trade execution
"""

import os
import sys
import hmac
import hashlib
import base64
import time
import requests
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/logs/coinbase_api.log')
        ]
    )
    return logging.getLogger(__name__)

class CoinbaseProAPIClient:
    def __init__(self):
        """
        Initialize Coinbase Pro API Client
        Reads credentials from .env file
        """
        # Load environment variables
        load_dotenv()
        
        # Setup logging
        self.logger = setup_logging()
        
        # Coinbase Pro API Configuration
        self.base_url = 'https://api.pro.coinbase.com'
        
        # API Credentials from .env
        self.api_key = os.getenv('COINBASE_API_KEY')
        self.api_secret = os.getenv('COINBASE_API_SECRET')
        
        # Validate credentials
        if not all([self.api_key, self.api_secret]):
            print("ERROR: Missing Coinbase API credentials in .env file.")
            print("Please ensure COINBASE_API_KEY and COINBASE_API_SECRET are set.")
            sys.exit(1)
    
    def _generate_signature(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """
        Generate Coinbase Pro API signature for authentication
        
        :param method: HTTP method (GET, POST, etc.)
        :param request_path: API endpoint path
        :param body: Request body (optional)
        :return: Headers for API authentication
        """
        timestamp = str(time.time())
        
        # Create message
        message = timestamp + method.upper() + request_path + body
        
        # Create signature
        try:
            signature = hmac.new(
                base64.b64decode(self.api_secret),
                message.encode('utf-8'),
                hashlib.sha256
            )
            signature_b64 = base64.b64encode(signature.digest()).decode('utf-8')
            
            # Return authentication headers
            return {
                'CB-ACCESS-KEY': self.api_key,
                'CB-ACCESS-SIGN': signature_b64,
                'CB-ACCESS-TIMESTAMP': timestamp,
                'Content-Type': 'application/json'
            }
        except Exception as e:
            print(f"Signature generation error: {e}")
            print("Check that your API secret is a valid base64-encoded string.")
            sys.exit(1)
    
    def get_product_ticker(self, product_id: str) -> Optional[float]:
        """
        Get current ticker price for a specific product
        
        :param product_id: Trading pair (e.g., 'BTC-USD')
        :return: Current price or None
        """
        try:
            response = requests.get(
                f"{self.base_url}/products/{product_id}/ticker",
                timeout=10
            )
            
            response.raise_for_status()
            ticker = response.json()
            
            price = float(ticker.get('price', 0))
            print(f"Ticker price for {product_id}: ${price}")
            
            return price
        
        except requests.exceptions.RequestException as e:
            print(f"Ticker fetch error for {product_id}: {e}")
            return None

def main():
    """
    Example usage and testing of Coinbase Pro API Client
    """
    try:
        client = CoinbaseProAPIClient()
        
        # Test product ticker
        test_pairs = ['BTC-USD', 'ETH-USD', 'XRP-USD']
        for pair in test_pairs:
            price = client.get_product_ticker(pair)
    
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()