#!/usr/bin/env python3
"""Debug: Print actual Coinbase order response."""

import os
import json
import time
import secrets
from dotenv import load_dotenv
import jwt
from cryptography.hazmat.primitives import serialization
import requests

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

api_key = os.getenv('COINBASE_API_KEY')
private_key_str = os.getenv('COINBASE_API_SECRET')

# Load key
private_key_bytes = private_key_str.encode('utf-8')
private_key_obj = serialization.load_pem_private_key(private_key_bytes, password=None)

# Build JWT
method = "POST"
path = "/api/v3/brokerage/orders"
host = "api.coinbase.com"
uri = f"{method} {host}{path}"

now = int(time.time())
jwt_payload = {
    'sub': api_key,
    'iss': 'cdp',
    'nbf': now,
    'exp': now + 120,
    'uri': uri,
}

jwt_token = jwt.encode(
    jwt_payload,
    private_key_obj,
    algorithm='ES256',
    headers={
        'kid': api_key,
        'nonce': secrets.token_hex(16),
    }
)

# Build order
body = {
    'client_order_id': secrets.token_hex(16),
    'product_id': 'BTC-USD',
    'side': 'BUY',
    'order_configuration': {
        'market_market_ioc': {
            'quote_size': '160.61'
        }
    }
}

# Make request
headers = {
    'Authorization': f'Bearer {jwt_token}',
    'Content-Type': 'application/json',
}

url = f"https://api.coinbase.com{path}"
response = requests.post(url, json=body, headers=headers, timeout=10)

print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Response body:")
print(json.dumps(response.json(), indent=2))
