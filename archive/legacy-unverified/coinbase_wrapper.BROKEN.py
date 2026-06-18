#!/usr/bin/env python3
"""
Coinbase Advanced Trade API Wrapper (ES256 JWT Authentication)
==============================================================

CORRECT IMPLEMENTATION: ES256 (ECDSA P-256) JWT authentication
Reference: https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication

No passphrase. No HMAC. Just ES256 JWT Bearer tokens.
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
    """
    
    def __init__(
        self,
        api_key: str,
        private_key: str,
        sandbox: bool = True
    ):
        """
        Initialize Coinbase Advanced Trade API wrapper.
        
        Args:
            api_key: "organizations/{org_id}/apiKeys/{key_id}"
            private_key: EC P-256 private key (PEM format)
            sandbox: Use sandbox (paper trading) mode
        """
        self.api_key = api_key
        self.private_key = private_key
        self.sandbox = sandbox
        
        # Base URLs
        if sandbox:
            self.base_url = "https://api-sandbox.coinbase.com"
        else:
            self.base_url = "https://api.coinbase.com"
        
        logger.info(f"✅ CoinbaseWrapper initialized ({('SANDBOX' if sandbox else 'LIVE')})")
        logger.info(f"   API Key: {api_key[:40]}...")
        logger.info(f"   Private Key loaded: {len(private_key)} chars")
    
    def build_jwt(self, method: str, path: str, body: str = "") -> str:
        """
        Build ES256 (ECDSA P-256) JWT for API request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/api/v3/brokerage/accounts")
            body: Request body (empty for GET)
        
        Returns:
            JWT token (expires in 120 seconds)
        """
        try:
            # Load private key
            private_key_bytes = self.private_key.encode('utf-8')
            private_key_obj = serialization.load_pem_private_key(
                private_key_bytes,
                password=None
            )
            
            # Build URI string: "METHOD host/path"
            host = "api.coinbase.com" if not self.sandbox else "api-sandbox.coinbase.com"
            uri = f"{method} {host}{path}"
            
            # Build JWT payload
            now = int(time.time())
            jwt_payload = {
                'sub': self.api_key,           # subject: our API key
                'iss': 'cdp',                   # issuer: Coinbase Developer Platform
                'nbf': now,                     # not before
                'exp': now + 120,               # expires in 120 seconds
                'uri': uri,                     # the URI we're calling
            }
            
            # Sign with ES256 (ECDSA P-256)
            jwt_token = jwt.encode(
                jwt_payload,
                private_key_obj,
                algorithm='ES256',
                headers={
                    'kid': self.api_key,                    # key ID
                    'nonce': secrets.token_hex(16),         # random nonce
                }
            )
            
            logger.debug(f"JWT generated for {method} {path}")
            return jwt_token
            
        except Exception as e:
            logger.error(f"JWT generation failed: {e}")
            raise ValueError(f"Cannot build JWT: {e}")
    
    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Coinbase API.
        
        Args:
            method: HTTP method
            path: API path
            body: Request body (for POST)
            timeout: Request timeout in seconds
        
        Returns:
            JSON response
        """
        try:
            # Build JWT
            body_str = json.dumps(body) if body else ""
            jwt_token = self.build_jwt(method, path, body_str)
            
            # Build request
            url = f"{self.base_url}{path}"
            headers = {
                'Authorization': f'Bearer {jwt_token}',
                'Content-Type': 'application/json',
            }
            
            # Make request
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=body, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check for errors
            if response.status_code >= 400:
                logger.error(f"{method} {path} returned {response.status_code}")
                logger.error(f"Response: {response.text}")
                response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Request failed: {method} {path} - {e}")
            raise
    
    def get_accounts(self) -> Dict[str, Any]:
        """Get list of accounts."""
        return self._request('GET', '/api/v3/brokerage/accounts')
    
    def get_price(self, product_id: str = "BTC-USD") -> Dict[str, Any]:
        """
        Get current price for product.
        
        Args:
            product_id: e.g., "BTC-USD"
        
        Returns:
            {'price': '62450.00', 'time': '...'}
        """
        try:
            response = self._request('GET', f'/api/v3/brokerage/product_ticker?product_id={product_id}')
            return {
                'price': float(response.get('price', 0)),
                'time': response.get('time', ''),
            }
        except Exception as e:
            logger.error(f"Failed to fetch price for {product_id}: {e}")
            return {'price': 0, 'time': ''}
    
    def place_market_buy(self, product_id: str, qty: float) -> Dict[str, Any]:
        """
        Place market buy order.
        
        Args:
            product_id: e.g., "BTC-USD"
            qty: Quantity to buy
        
        Returns:
            Order response
        """
        try:
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'BUY',
                'order_configuration': {
                    'market_market_ioc': {
                        'quote_size': f"{qty:.6f}"
                    }
                }
            }
            response = self._request('POST', '/api/v3/brokerage/orders', body)
            return {
                'id': response.get('order_id', ''),
                'status': response.get('order_status', 'PENDING'),
                'success': True
            }
        except Exception as e:
            logger.error(f"Market buy failed: {e}")
            return {'id': '', 'status': 'FAILED', 'success': False, 'error': str(e)}
    
    def place_market_sell(self, product_id: str, qty: float) -> Dict[str, Any]:
        """
        Place market sell order.
        """
        try:
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'SELL',
                'order_configuration': {
                    'market_market_ioc': {
                        'base_size': f"{qty:.6f}"
                    }
                }
            }
            response = self._request('POST', '/api/v3/brokerage/orders', body)
            return {
                'id': response.get('order_id', ''),
                'status': response.get('order_status', 'PENDING'),
                'success': True
            }
        except Exception as e:
            logger.error(f"Market sell failed: {e}")
            return {'id': '', 'status': 'FAILED', 'success': False, 'error': str(e)}
    
    def get_orders(self, product_id: Optional[str] = None) -> Dict[str, Any]:
        """Get orders (optionally filtered by product)."""
        path = '/api/v3/brokerage/orders/historical/batch'
        if product_id:
            path += f'?product_id={product_id}'
        return self._request('GET', path)
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        body = {'order_id': order_id}
        return self._request('POST', '/api/v3/brokerage/orders/batch/cancel', body)
