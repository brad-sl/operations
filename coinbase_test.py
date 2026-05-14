#!/usr/bin/env python3
"""
Simple Coinbase API Connection Test
Tests connectivity with provided credentials
"""

import os
import sys
import requests
import hashlib
import hmac
import time
from dotenv import load_dotenv

# Setup basic logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get credentials
API_KEY = os.getenv('COINBASE_API_KEY')
API_SECRET = os.getenv('COINBASE_API_SECRET')

# Check if credentials are provided
if not API_KEY or not API_SECRET:
    logger.error("Missing Coinbase API credentials. Please set COINBASE_API_KEY and COINBASE_API_SECRET in .env")
    sys.exit(1)

# Test endpoints
# Coinbase Pro (Exchange)
EXCHANGE_BASE_URL = "https://api.exchange.coinbase.com"
# Coinbase App API (Retail)
APP_BASE_URL = "https://api.coinbase.com"

class CoinbaseConnectionTester:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def sign_request(self, method, path, body=''):
        """
        Sign a request for Coinbase Pro/Exchange API
        """
        timestamp = str(int(time.time()))
        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        return timestamp, signature
    
    def test_exchange_accounts(self):
        """
        Test connection to Coinbase Exchange/Pro API - Get accounts
        """
        path = '/accounts'
        method = 'GET'
        timestamp, signature = self.sign_request(method, path)
        
        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp
        }
        
        try:
            response = requests.get(f"{EXCHANGE_BASE_URL}{path}", headers=headers, timeout=10)
            logger.info(f"Exchange API Response (Accounts): {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Success! Connected to Coinbase Exchange API")
                data = response.json()
                logger.info(f"Account Data: {data[:2]}... (limited to first 2 for brevity)")
            else:
                logger.error(f"Failed to connect. Response: {response.text[:200]}...")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error connecting to Exchange API: {e}")
            return False
    
    def test_app_accounts(self):
        """
        Test connection to Coinbase App API - Get accounts
        """
        path = '/v2/accounts'
        timestamp = str(int(time.time()))
        message = f"{timestamp}GET{path}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        headers = {
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-VERSION': '2021-01-01'
        }
        
        try:
            response = requests.get(f"{APP_BASE_URL}{path}", headers=headers, timeout=10)
            logger.info(f"App API Response (Accounts): {response.status_code}")
            if response.status_code == 200:
                logger.info(f"Success! Connected to Coinbase App API")
                data = response.json()
                logger.info(f"Account Data: {data}")
            else:
                logger.error(f"Failed to connect. Response: {response.text[:200]}...")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error connecting to App API: {e}")
            return False

def main():
    logger.info("Starting Coinbase API Connection Test")
    tester = CoinbaseConnectionTester(API_KEY, API_SECRET)
    
    logger.info("\n=== Testing Coinbase Exchange/Pro API ===")
    exchange_success = tester.test_exchange_accounts()
    
    logger.info("\n=== Testing Coinbase App API ===")
    app_success = tester.test_app_accounts()
    
    if exchange_success:
        logger.info("\nSUCCESS: Connected to Coinbase Exchange/Pro API. Use this for trading.")
    elif app_success:
        logger.info("\nSUCCESS: Connected to Coinbase App API. Use this for personal account access.")
    else:
        logger.error("\nFAILED: Could not connect to any Coinbase API. Check credentials or API key permissions.")
        logger.error("Common issues:")
        logger.error("1. API key is invalid or revoked")
        logger.error("2. API key doesn't have correct permissions")
        logger.error("3. API key is for a different Coinbase platform")
        logger.error("Visit https://www.coinbase.com/settings/api or https://pro.coinbase.com/profile/api to verify/generate keys")

if __name__ == '__main__':
    main()