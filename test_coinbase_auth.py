#!/usr/bin/env python3
"""Test Coinbase Advanced Trade API credentials"""

import os
from dotenv import load_dotenv
from coinbase.rest import RESTClient

load_dotenv()

api_key = os.getenv('COINBASE_API_KEY')
api_secret = os.getenv('COINBASE_API_SECRET')

print(f"Testing credentials:")
print(f"  API_KEY: {api_key[:15]}...")
print(f"  API_SECRET length: {len(api_secret) if api_secret else 0}")

try:
    client = RESTClient(api_key=api_key, api_secret=api_secret)
    print("✅ Client initialized")
    
    # Test product fetch (read access)
    product = client.get_product('BTC-USD')
    price = product.price  # Response object attribute, not dict
    print(f"✅ Auth SUCCESS: BTC-USD = ${price}")
    print(f"✅ Coinbase Advanced Trade API credentials VALID")
    
except Exception as e:
    print(f"❌ Auth FAILED: {e}")
    print(f"Error type: {type(e).__name__}")
