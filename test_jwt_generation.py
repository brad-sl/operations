#!/usr/bin/env python3
"""Debug JWT generation to verify ES256 signature."""

import os
import time
import secrets
import jwt
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

api_key = os.getenv('COINBASE_API_KEY')
private_key_str = os.getenv('COINBASE_API_SECRET')

print(f"API Key: {api_key}")
print(f"Private Key (first 50 chars): {private_key_str[:50]}...")
print()

# Try to load the key
try:
    private_key_bytes = private_key_str.encode('utf-8')
    private_key_obj = serialization.load_pem_private_key(private_key_bytes, password=None)
    print(f"✅ Private key loaded successfully")
    print(f"   Key type: {type(private_key_obj)}")
    print()
except Exception as e:
    print(f"❌ Failed to load private key: {e}")
    exit(1)

# Build JWT
method = "GET"
path = "/api/v3/brokerage/accounts"
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

print(f"JWT Payload:")
print(f"  sub: {api_key}")
print(f"  iss: cdp")
print(f"  nbf: {now}")
print(f"  exp: {now + 120}")
print(f"  uri: {uri}")
print()

# Sign
try:
    jwt_token = jwt.encode(
        jwt_payload,
        private_key_obj,
        algorithm='ES256',
        headers={
            'kid': api_key,
            'nonce': secrets.token_hex(16),
        }
    )
    print(f"✅ JWT generated successfully")
    print(f"   Token length: {len(jwt_token)} chars")
    print(f"   Token: {jwt_token[:100]}...{jwt_token[-30:]}")
    print()
    
    # Decode to check contents
    decoded = jwt.decode(jwt_token, options={"verify_signature": False})
    print(f"Decoded JWT:")
    for key, val in decoded.items():
        print(f"   {key}: {val}")
    
except Exception as e:
    print(f"❌ JWT encoding failed: {e}")
    import traceback
    traceback.print_exc()
