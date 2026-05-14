#!/usr/bin/env python3
"""
Coinbase Advanced API Client - Direct SDK Integration
Uses official coinbase-advanced-py SDK (v1.8.2) with optimized product fetching
"""

import os
import sys
import logging
import time
import json
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv

try:
    from coinbase.rest import RESTClient
except ImportError:
    print("ERROR: pip install coinbase-advanced-py")
    sys.exit(1)

class OrderResponse:
    """Compatible response wrapper for OrderExecutor"""
    def __init__(self, success, order_id=None, error=None, **kwargs):
        self.success = success
        self.order_id = order_id
        self.error = error

def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/logs/phase5_live.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

class CoinbaseAdvancedClient:
    def __init__(self, test_mode: bool = False):
        # Load explicit .env path
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        ENV_PATH = os.path.join(SCRIPT_DIR, '.env')
        load_dotenv(ENV_PATH)
        
        self.logger = setup_logging()
        self.test_mode = test_mode
        
        # Get credentials
        api_key = os.getenv('COINBASE_API_KEY')
        api_secret = os.getenv('COINBASE_API_SECRET')
        
        # Unescape EC private key if it contains escaped newlines
        if api_secret and '\\n' in api_secret:
            api_secret = api_secret.encode().decode('unicode_escape')
        
        try:
            if not api_key or not api_secret:
                raise ValueError("Missing Coinbase API credentials")
            
            self.client = RESTClient(
                api_key=api_key,
                api_secret=api_secret
            )
            self.logger.info(f"✅ Coinbase SDK initialized (Sandbox Mode: {test_mode})")
        except Exception as e:
            self.logger.error(f"❌ Failed to init: {e}")
            raise

    def get_batch_prices(self, product_ids: List[str]) -> Dict[str, float]:
        """
        Fetch current prices for products using individual get_product() calls.
        Avoids the massive get_products() which causes JSON parsing errors.
        """
        prices = {}
        
        for product_id in product_ids:
            try:
                # Use get_product() for individual products, not get_products() for all
                product = self.client.get_product(product_id=product_id)
                if hasattr(product, 'price'):
                    prices[product_id] = float(product.price)
                    self.logger.debug(f"Fetched {product_id}: ${product.price}")
                else:
                    self.logger.warning(f"No price field in response for {product_id}")
                    prices[product_id] = 0.0
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON parse error for {product_id}: {str(e)[:100]}")
                prices[product_id] = 0.0
            except Exception as e:
                self.logger.warning(f"Failed to fetch price for {product_id}: {str(e)[:200]}")
                prices[product_id] = 0.0
        
        self.logger.info(f"✅ Batch price fetch: {len([p for p in prices.values() if p > 0])}/{len(product_ids)} successful")
        return prices

    def get_price(self, product_id: str) -> float:
        """Single product price (OrderExecutor compat)"""
        prices = self.get_batch_prices([product_id])
        return prices.get(product_id, 0.0)

    def create_order(self, product_id: str, side: str, size: float, **kwargs):
        """Create market order (OrderExecutor compat)"""
        import uuid
        try:
            # Generate unique client order ID for idempotency (REQUIRED parameter)
            client_order_id = str(uuid.uuid4())
            
            if side.lower() == 'buy':
                # market_order_buy(client_order_id, product_id, quote_size)
                order = self.client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    quote_size=str(size)
                )
            else:
                # market_order_sell(client_order_id, product_id, base_size)
                order = self.client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=product_id,
                    base_size=str(size)
                )
            
            order_id = order.order_id if hasattr(order, 'order_id') else str(order)
            self.logger.info(f"✅ Order executed: {side} {product_id} size={size}, order_id={order_id}")
            return OrderResponse(success=True, order_id=order_id)
        except Exception as e:
            self.logger.error(f"Order failed for {product_id}: {e}")
            return OrderResponse(success=False, error=str(e))

def main():
    """Quick test"""
    client = CoinbaseAdvancedClient(test_mode=True)
    prices = client.get_batch_prices(['BTC-USD', 'ETH-USD', 'ADA-USD'])
    print("\n=== Current Prices ===")
    for pair, price in prices.items():
        print(f"{pair}: ${price:.2f}")

if __name__ == "__main__":
    main()
