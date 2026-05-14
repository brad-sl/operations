#!/usr/bin/env python3
"""Test authentication in SANDBOX mode to verify JWT + key work."""

import os
from dotenv import load_dotenv
from coinbase_wrapper import CoinbaseWrapper

load_dotenv('/home/brad/.openclaw/workspace/operations/crypto-bot/.env')

api_key = os.getenv('COINBASE_API_KEY')
private_key = os.getenv('COINBASE_API_SECRET')

print("Testing SANDBOX mode first...")
print()

try:
    wrapper = CoinbaseWrapper(api_key, private_key, sandbox=True)
    print("✅ Sandbox wrapper initialized")
    print()
    
    print("Fetching accounts from SANDBOX...")
    accounts = wrapper.get_accounts()
    print(f"✅ SUCCESS! Accounts: {accounts}")
    
except Exception as e:
    print(f"❌ SANDBOX failed: {e}")
    print()

print()
print("Testing LIVE mode...")
try:
    wrapper_live = CoinbaseWrapper(api_key, private_key, sandbox=False)
    print("✅ Live wrapper initialized")
    print()
    
    print("Fetching accounts from LIVE...")
    accounts_live = wrapper_live.get_accounts()
    print(f"✅ SUCCESS! Accounts: {accounts_live}")
    
except Exception as e:
    print(f"❌ LIVE failed: {e}")
