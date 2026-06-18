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
from typing import Dict, List, Optional, Any
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

    def place_stop_limit_sell(self, product_id: str, qty: float, stop_price: float, limit_price: float):
        """
        Places a stop-limit sell order via SDK.
        """
        import uuid
        client_order_id = str(uuid.uuid4())
        try:
            # stop_limit_order_gtc_sell
            order = self.client.stop_limit_order_gtc_sell(
                client_order_id=client_order_id,
                product_id=product_id,
                base_size=str(qty),
                stop_price=str(stop_price),
                limit_price=str(limit_price)
            )
            self.logger.info(f"✅ SL Order placed: {product_id} qty={qty}, stop={stop_price}, limit={limit_price}, id={getattr(order, 'order_id', str(order))}")
            return True
        except Exception as e:
            self.logger.error(f"SL Order failed for {product_id}: {e}")
            return False

    def cancel_order(self, order_id: str):
        """Cancels a single order."""
        try:
            self.client.cancel_orders(order_ids=[order_id])
            return True
        except Exception as e:
            self.logger.error(f"Cancel order failed: {order_id}, {e}")
            return False

    def get_product_metadata(self, product_id: str):
        """Returns mock metadata for testing; normally fetches from API."""
        return {"price_increment": "0.0001", "base_increment": "0.00000001"}

    def _quantize_price(self, price: float, increment: str) -> str:
        from decimal import Decimal, ROUND_DOWN
        inc = Decimal(increment)
        return str((Decimal(str(price)) // inc) * inc)

    def _quantize_size(self, size: float, increment: str) -> str:
        from decimal import Decimal, ROUND_DOWN
        inc = Decimal(increment)
        return str((Decimal(str(size)) // inc) * inc)

    def get_accounts(self) -> Dict[str, Any]:
        """Fetch all accounts from Coinbase using SDK. Returns shape expected by LivePortfolioManager."""
        from typing import Any
        try:
            response = self.client.get_accounts()
            accounts_list = []
            if hasattr(response, 'accounts') and response.accounts:
                for acc in response.accounts:
                    # Normalize SDK Account object to dict
                    currency = getattr(acc, 'currency', None)
                    avail = getattr(acc, 'available_balance', None)
                    if avail is not None:
                        if hasattr(avail, 'value'):
                            avail_dict = {'value': str(getattr(avail, 'value', '0'))}
                        else:
                            avail_dict = {'value': str(avail.get('value', '0')) if isinstance(avail, dict) else '0'}
                    else:
                        avail_dict = {'value': '0'}
                    balance_val = getattr(acc, 'balance', None)
                    if balance_val is None:
                        balance_val = avail_dict.get('value', '0')
                    accounts_list.append({
                        'currency': currency,
                        'available_balance': avail_dict,
                        'balance': str(balance_val) if balance_val else '0',
                        'asset': currency,  # alias
                    })
            self.logger.info(f"✅ get_accounts: fetched {len(accounts_list)} accounts")
            return {'accounts': accounts_list}
        except Exception as e:
            self.logger.error(f"get_accounts failed: {e}")
            return {'accounts': []}

    def get_account_balances(self) -> Dict[str, Any]:
        """Alias / alternative name expected by some managers. Same shape as get_accounts."""
        return self.get_accounts()

def main():
    """Quick test"""
    client = CoinbaseAdvancedClient(test_mode=True)
    prices = client.get_batch_prices(['BTC-USD', 'ETH-USD', 'ADA-USD'])
    print("\n=== Current Prices ===")
    for pair, price in prices.items():
        print(f"{pair}: ${price:.2f}")

if __name__ == "__main__":
    main()
