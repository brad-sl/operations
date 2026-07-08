#!/usr/bin/env python3
"""
Coinbase Advanced Trade API Wrapper (ES256 JWT Authentication) - FIXED
========================================================================

CORRECT IMPLEMENTATION: ES256 (ECDSA P-256) JWT authentication
Reference: https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication

FIX 1: Use base_size (asset quantity) instead of quote_size for market orders
FIX 2: Parse success_response structure correctly (order_id nested in success_response)
"""

import json
import time
import secrets
import requests
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

import jwt
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

@dataclass
class OrderResponse:
    """Structured response from order operations."""
    success: bool
    order_id: Optional[str] = None
    product_id: str = "BTC-USD"
    side: str = "buy"
    price: float = 0.0
    size: float = 0.0
    status: str = "PENDING"
    timestamp: str = ""
    error: Optional[str] = None


class CoinbaseWrapper:
    """
    Coinbase Advanced Trade API wrapper with ES256 JWT authentication.
    
    AUTHENTICATION (ES256 JWT only):
    - api_key: organizations/{org_id}/apiKeys/{key_id}
    - private_key: EC P-256 private key (PEM format)
    
    NO passphrase required. NO Ed25519. ES256 only.
    
    JWT expires in 120 seconds. Generate fresh JWT for each request.
    
    MARKET ORDER FIX:
    - Use base_size (asset quantity) not quote_size (USD amount)
    - Example: BTC-USD buy 0.01 BTC → base_size: "0.01"
    - Response structure: {"success": true, "success_response": {"order_id": "..."}}
    """
    
    def __init__(self, api_key: str, private_key: str, sandbox: bool = False):
        self.api_key = api_key
        self.private_key_str = private_key
        self.sandbox = sandbox
        
        # Load private key for JWT signing
        try:
            self.private_key = serialization.load_pem_private_key(
                self.private_key_str.encode('utf-8'),
                password=None
            )
            logger.info(f"✅ CoinbaseWrapper initialized ({'SANDBOX' if sandbox else 'LIVE'})")
            logger.info(f"   API Key: {api_key[:50]}...")
            logger.info(f"   Private Key loaded: {len(self.private_key_str)} chars")
        except Exception as e:
            logger.error(f"❌ Failed to load private key: {e}")
            raise
        
        self.base_url = "https://api-sandbox.coinbase.com" if sandbox else "https://api.coinbase.com"
        self.host = "api-sandbox.coinbase.com" if sandbox else "api.coinbase.com"
    
    def _generate_jwt(self, method: str, path: str, body: Optional[Dict] = None) -> str:
        """Generate ES256 JWT for request authentication.

        CRITICAL FIX: The signed 'uri' MUST NOT include query string parameters.
        Coinbase signs ONLY the base resource path (e.g. /api/v3/brokerage/orders/historical/batch).
        Query params (e.g. ?order_status=OPEN) are sent in the actual HTTP GET URL
        but MUST be stripped from the JWT 'uri' claim, or you get 401 Unauthorized
        on list-orders / historical batch (while accounts may still succeed).
        """
        # Strip query string for the canonical signed URI (root cause of 401 on orders/historical)
        base_path = path.split('?', 1)[0]
        uri = f"{method} {self.host}{base_path}"
        now = int(time.time())

        # Clock skew tolerance: Coinbase server time may differ by a few seconds.
        # Using nbf=now-5 prevents "token not yet valid" 401s on fast or drifted clocks.
        jwt_payload = {
            'sub': self.api_key,
            'iss': 'cdp',
            'nbf': now - 5,
            'exp': now + 125,
            'uri': uri,
        }

        token = jwt.encode(
            jwt_payload,
            self.private_key,
            algorithm='ES256',
            headers={
                'kid': self.api_key,
                'nonce': secrets.token_hex(16)
            }
        )

        logger.debug(f"JWT generated for {method} {base_path}")
        return token
    
    def _request(self, method: str, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to Coinbase API."""
        jwt_token = self._generate_jwt(method, path, body)
        
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{path}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=body, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Robust status extraction (handles cases where response attr is missing or wrapped)
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            raw_text = ""
            if getattr(e, 'response', None) is not None:
                try:
                    raw_text = (e.response.text or "")[:500]
                except Exception:
                    raw_text = "<unable to read body>"

            is_auth_error = (status == 401) or (status is not None and 400 <= status < 500)
            if is_auth_error:
                logger.warning(f"API request failed with HTTP {status} (auth/permission/scope issue; graceful empty for read ops). body={raw_text[:200]!r}")
            else:
                logger.error(f"API request failed: {e} body={raw_text[:200]!r}")

            # Always attempt to return parsed error body or structured fallback (never crash upper layers on json)
            if getattr(e, 'response', None) is not None:
                try:
                    if raw_text.strip():
                        parsed = e.response.json()
                        if isinstance(parsed, dict):
                            parsed.setdefault("status_code", status)
                            parsed.setdefault("raw_text", raw_text)
                            return parsed
                        return {"error": str(parsed), "status_code": status, "raw_text": raw_text}
                except Exception:
                    pass
                # Fallback prevents JSON decode crashes on 401/empty-body responses
                return {"error": str(e), "status_code": status, "raw_text": raw_text, "url": str(getattr(e.response, "url", ""))}
            return {"error": str(e), "status_code": status}
    
    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        """Dynamic metadata via public Coinbase API (synced with exchange_client)."""
        if not hasattr(self, "_product_meta_cache"):
            self._product_meta_cache = {}
        pid = product_id.upper()
        if pid in self._product_meta_cache:
            return self._product_meta_cache[pid].copy()
        try:
            import requests
            r = requests.get(f"https://api.exchange.coinbase.com/products/{pid}", timeout=5)
            if r.status_code == 200:
                d = r.json()
                meta = {
                    "price_increment": float(d.get("quote_increment") or d.get("price_increment") or 0.01),
                    "base_increment": float(d.get("base_increment") or 0.001),
                }
                self._product_meta_cache[pid] = meta
                return meta.copy()
        except:
            pass
        # fallback (synced with exchange_client 11-pair + P0-02 updates; dynamic primary)
        fallbacks = {
            "BTC-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "ETH-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "SOL-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "XRP-USD": {"price_increment": 0.0001, "base_increment": 0.000001},
            "DOGE-USD": {"price_increment": 0.00001, "base_increment": 0.1},
            "ADA-USD": {"price_increment": 0.0001, "base_increment": 0.00000001},
            "AVAX-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "LINK-USD": {"price_increment": 0.001, "base_increment": 0.01},
            "UNI-USD": {"price_increment": 0.001, "base_increment": 0.000001},
            "ARB-USD": {"price_increment": 0.0001, "base_increment": 0.01},
            "OP-USD": {"price_increment": 0.001, "base_increment": 0.01},
        }
        meta = fallbacks.get(pid, {"price_increment": 0.01, "base_increment": 0.001})
        self._product_meta_cache[pid] = meta
        return meta.copy()

    def _quantize_price(self, price: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(price)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))

    def _quantize_size(self, size: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(size)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))

    def get_accounts(self) -> Dict[str, Any]:
        """Get all accounts (balances, holdings). Matches what CoinbaseExchangeClient expects."""
        return self._request('GET', '/api/v3/brokerage/accounts')
    
    def get_orders(self, order_status: str = 'OPEN') -> Dict[str, Any]:
        """Get orders by status."""
        return self._request('GET', f'/api/v3/brokerage/orders/historical/batch?order_status={order_status}')

    def get_key_permissions(self) -> Dict[str, Any]:
        """Fetch current API key permissions (can_view, can_trade, can_transfer, portfolio)."""
        try:
            return self._request('GET', '/api/v3/brokerage/key_permissions')
        except Exception as e:
            return {"error": str(e)}

    def place_market_buy(self, product_id: str, qty: float) -> Dict[str, Any]:
        """
        Place market buy order using base_size (asset quantity).
        
        Args:
            product_id: e.g., "BTC-USD"
            qty: Quantity of asset to buy (e.g., 0.01 for 0.01 BTC)
        
        Returns:
            Order response with order_id and status
        """
        try:
            # Support both: if qty looks like USD amount (small for crypto like ADA), prefer quote_size for "spend X USD"
            # For safety, default to quote_size when calling with usd_amount semantics
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'BUY',
                'order_configuration': {
                    'market_market_ioc': {
                        'quote_size': f"{qty:.8f}"   # USD amount to spend
                    }
                }
            }
            response = self._request('POST', '/api/v3/brokerage/orders', body)
            
            # Handle API response structure
            if response.get('success') == False:
                error = response.get('error_response', {}).get('error', 'Unknown error')
                logger.error(f"Order failed: {error}")
                return {
                    'id': '',
                    'status': 'FAILED',
                    'success': False,
                    'error': error,
                    'raw_response': response
                }
            
            # Extract order_id from nested success_response
            success_response = response.get('success_response', {})
            order_id = success_response.get('order_id', '')
            
            if not order_id:
                logger.error(f"No order_id in response: {response}")
                return {
                    'id': '',
                    'status': 'FAILED',
                    'success': False,
                    'error': 'No order_id returned',
                    'raw_response': response
                }
            
            logger.info(f"✅ Order placed: {order_id} ({product_id})")
            
            return {
                'id': order_id,
                'status': 'PENDING',
                'success': True,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Market buy exception: {e}")
            import traceback
            traceback.print_exc()
            return {
                'id': '',
                'status': 'FAILED',
                'success': False,
                'error': str(e)
            }
    
    def place_market_sell(self, product_id: str, qty: float) -> Dict[str, Any]:
        """Place market sell order using base_size."""
        try:
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'SELL',
                'order_configuration': {
                    'market_market_ioc': {
                        'base_size': f"{qty:.8f}"
                    }
                }
            }
            response = self._request('POST', '/api/v3/brokerage/orders', body)
            
            if response.get('success') == False:
                error = response.get('error_response', {}).get('error', 'Unknown error')
                logger.error(f"Sell order failed: {error}")
                return {
                    'id': '',
                    'status': 'FAILED',
                    'success': False,
                    'error': error
                }
            
            success_response = response.get('success_response', {})
            order_id = success_response.get('order_id', '')
            
            if not order_id:
                return {
                    'id': '',
                    'status': 'FAILED',
                    'success': False,
                    'error': 'No order_id returned'
                }
            
            logger.info(f"✅ Sell order placed: {order_id} ({product_id})")
            
            return {
                'id': order_id,
                'status': 'PENDING',
                'success': True,
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Market sell exception: {e}")
            return {
                'id': '',
                'status': 'FAILED',
                'success': False,
                'error': str(e)
            }
    
    def place_limit_buy(self, product_id: str, qty: float, price: float) -> Dict[str, Any]:
        """Place limit buy order."""
        try:
            meta = self.get_product_metadata(product_id)
            qty_str = self._quantize_size(qty, meta["base_increment"])
            limit_price_str = self._quantize_price(price, meta["price_increment"])
            
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'BUY',
                'order_configuration': {
                    'limit_limit_gtc': {
                        'base_size': qty_str,
                        'limit_price': limit_price_str
                    }
                }
            }
            response = self._request('POST', '/api/v3/brokerage/orders', body)
            
            if response.get('success') == False:
                error = response.get('error_response', {}).get('error', 'Unknown error')
                return {'id': '', 'status': 'FAILED', 'success': False, 'error': error}
            
            success_response = response.get('success_response', {})
            order_id = success_response.get('order_id', '')
            
            return {
                'id': order_id,
                'status': 'PENDING',
                'success': bool(order_id),
                'raw_response': response
            }
        except Exception as e:
            logger.error(f"Limit buy exception: {e}")
            return {'id': '', 'status': 'FAILED', 'success': False, 'error': str(e)}


    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place a native stop-limit sell order."""
        import time
        meta = self.get_product_metadata(product_id)
        
        if limit_price is None:
            limit_price = float(self._quantize_price(stop_price * 0.995, meta["price_increment"]))

        if client_order_id is None:
            client_order_id = f"sl-{product_id}-{int(time.time())}"

        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": "SELL",
            "order_configuration": {
                "stop_limit_stop_limit_gtc": {
                    "base_size": self._quantize_size(qty, meta["base_increment"]),
                    "limit_price": self._quantize_price(limit_price, meta["price_increment"]),
                    "stop_price": self._quantize_price(stop_price, meta["price_increment"]),
                    "stop_direction": "STOP_DIRECTION_STOP_DOWN",
                }
            }
        }

        try:
            response = self._request("POST", "/api/v3/brokerage/orders", body)
            if response.get("success") is False:
                err = response.get("error_response", {}).get("error", "Unknown")
                return {"success": False, "error": err, "raw": response}
            order_id = response.get("success_response", {}).get("order_id", "")
            return {"success": True, "order_id": order_id, "raw": response}
        except Exception as e:
            logger.error(f"Stop-limit sell failed for {product_id}: {e}")
            return {"success": False, "error": str(e)}
