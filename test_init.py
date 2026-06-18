
import sys
import os
import logging

# Add project root to path
sys.path.append('/home/brad/projects/crypto-trading-bot')

# Ensure environment vars are loaded for testing
from dotenv import load_dotenv
load_dotenv('/home/brad/projects/crypto-trading-bot/.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_init")

try:
    from phase6.core.exchange_client import CoinbaseExchangeClient
    # Instantiate with mode="shadow" to avoid actual API connection errors for now
    client = CoinbaseExchangeClient(mode="shadow")
    print("✅ CoinbaseExchangeClient initialized successfully in shadow mode.")
except Exception as e:
    logger.exception(f"❌ Initialization failed: {e}")
    sys.exit(1)
