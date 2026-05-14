#!/usr/bin/env python3
"""
Coinbase Pro API Client for Trading
Uses API credentials for authenticated requests
"""

import os
import sys
import requests
import hashlib
import hmac
import time
import json
from dotenv import load_dotenv

import logging

# Setup logging
log_dir = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs'
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, 'coinbase_pro.log'))
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get credentials
API_KEY = os.getenv('COINBASE_API_KEY')
API_SECRET = os.getenv('COINBASE_API_SECRET')
API_PASSPHRASE = os.getenv('COINBASE_PASSPHRASE', '')  # Optional, default to empty if not set

# Check if required credentials are provided
if not API_KEY or not API_SECRET:
    logger.error("Missing required Coinbase API credentials. Please set COINBASE_API_KEY and COINBASE_API_SECRET in .env")
    sys.exit(1)
else:
    logger.info("API Key and Secret loaded. Passphrase: %s", "Set" if API_PASSPHRASE else "Not Set")

# Coinbase Pro API endpoints
BASE_URL = "https://api.exchange.coinbase.com"

class CoinbaseProClient:
    def __init__(self, api_key, api_secret, api_passphrase=''):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase

    def sign_request(self, method, path, body=''):
        """
        Sign a request for Coinbase Pro API
        """
        timestamp = str(int(time.time()))
        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    def get_accounts(self):
        """
        Get account information
        """
        path = '/accounts'
        method = 'GET'
        timestamp, signature = self.sign_request(method, path)

        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }
        if self.api_passphrase:
            headers['CB-ACCESS-PASSPHRASE'] = self.api_passphrase
            logger.info("Using passphrase in request headers")
        else:
            logger.warning("No passphrase provided; proceeding without it")

        try:
            logger.info(f"Local timestamp: {timestamp}, Server time check recommended")
            response = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
            logger.info(f"API Response (Accounts): {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Success! Connected to Coinbase Pro API")
                data = response.json()
                logger.info(f"Account Data: {data[:2] if len(data) > 2 else data}...")
                return data
            else:
                logger.error(f"Failed to connect. Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error connecting to Coinbase Pro API: {e}")
            return None

    def get_product_ticker(self, product_id):
        """
        Get current ticker for a product
        """
        path = f'/products/{product_id}/ticker'
        method = 'GET'
        timestamp, signature = self.sign_request(method, path)

        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }
        if self.api_passphrase:
            headers['CB-ACCESS-PASSPHRASE'] = self.api_passphrase
            logger.info("Using passphrase in request headers")
        else:
            logger.warning("No passphrase provided; proceeding without it")

        try:
            logger.info(f"Local timestamp: {timestamp}, Server time check recommended")
            response = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
            logger.info(f"API Response (Ticker for {product_id}): {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Ticker Data: {data}")
                return data
            else:
                logger.error(f"Failed to get ticker. Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting ticker for {product_id}: {e}")
            return None

    def get_order_book(self, product_id, level=2):
        """
        Get order book for a product
        """
        path = f'/products/{product_id}/book?level={level}'
        method = 'GET'
        timestamp, signature = self.sign_request(method, path)

        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }
        if self.api_passphrase:
            headers['CB-ACCESS-PASSPHRASE'] = self.api_passphrase
            logger.info("Using passphrase in request headers")
        else:
            logger.warning("No passphrase provided; proceeding without it")

        try:
            logger.info(f"Local timestamp: {timestamp}, Server time check recommended")
            response = requests.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
            logger.info(f"API Response (Order Book for {product_id}): {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Order Book Data (limited): Bids {data.get('bids', [])[:2] if data.get('bids') else 'N/A'}, Asks {data.get('asks', [])[:2] if data.get('asks') else 'N/A'}")
                return data
            else:
                logger.error(f"Failed to get order book. Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting order book for {product_id}: {e}")
            return None

    def place_market_order(self, product_id, side, funds=None, size=None):
        """
        Place a market order
        """
        path = '/orders'
        method = 'POST'
        
        order_data = {
            'product_id': product_id,
            'side': side.upper(),
            'type': 'market',
            'client_oid': str(time.time())
        }
        if funds:
            order_data['funds'] = str(funds)
        if size:
            order_data['size'] = str(size)

        body = json.dumps(order_data)
        timestamp, signature = self.sign_request(method, path, body)

        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }
        if self.api_passphrase:
            headers['CB-ACCESS-PASSPHRASE'] = self.api_passphrase
            logger.info("Using passphrase in request headers")
        else:
            logger.warning("No passphrase provided; proceeding without it")

        try:
            logger.info(f"Local timestamp: {timestamp}, Server time check recommended")
            response = requests.post(f"{BASE_URL}{path}", headers=headers, data=body, timeout=10)
            logger.info(f"API Response (Order for {product_id}): {response.status_code}")
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Order Successful: {data}")
                return data
            else:
                logger.error(f"Failed to place order. Response: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error placing order for {product_id}: {e}")
            return None

def main():
    logger.info("Starting Coinbase Pro API Test with New Credentials")
    client = CoinbaseProClient(API_KEY, API_SECRET, API_PASSPHRASE)
    
    logger.info("\n=== Testing Account Access ===")
    accounts = client.get_accounts()
    if accounts:
        logger.info(f"Found {len(accounts)} account(s)")
        for acct in accounts:
            if isinstance(acct, dict) and 'balance' in acct and 'currency' in acct:
                logger.info(f"Account {acct.get('name', 'Unnamed')}: {acct['balance']} {acct['currency']}")
    
    logger.info("\n=== Testing Product Ticker ===")
    ticker = client.get_product_ticker('BTC-USD')
    if ticker and 'price' in ticker:
        logger.info(f"Current BTC-USD Price: ${ticker['price']}")
    
    logger.info("\n=== Testing Order Book ===")
    order_book = client.get_order_book('BTC-USD')
    if order_book:
        logger.info(f"Successfully retrieved order book for BTC-USD")
    
    # Uncomment to test placing a small order (be cautious with real funds)
    # logger.info("\n=== Testing Market Order ===")
    # order = client.place_market_order('BTC-USD', 'buy', funds=10.0)
    # if order:
    #     logger.info(f"Order placed successfully: {order}")
    
    logger.info("Test Complete")

if __name__ == '__main__':
    main()