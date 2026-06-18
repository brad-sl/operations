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
        """Generate ES256 JWT for request authentication."""
        uri = f"{method} {self.host}{path}"
        now = int(time.time())
        
        jwt_payload = {
            'sub': self.api_key,
            'iss': 'cdp',
            'nbf': now,
            'exp': now + 120,
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
        
        logger.debug(f"JWT generated for {method} {path}")
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
            
            # Try to parse JSON, handling corrupted responses
            try:
                return response.json()
            except json.JSONDecodeError as json_err:
                logger.warning(f"JSON decode error: {json_err}. Attempting recovery...")
                # Try to extract first valid JSON object from response text
                text = response.text.strip()
                decoder = json.JSONDecoder()
                try:
                    obj, idx = decoder.raw_decode(text)
                    logger.info(f"Successfully recovered JSON object (consumed {idx}/{len(text)} chars)")
                    return obj
                except json.JSONDecodeError:
                    logger.error(f"Could not recover JSON from response: {text[:200]}")
                    return {'error': f'JSONDecodeError: {json_err}', 'raw_response': text[:1000]}
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            if hasattr(e.response, 'json'):
                return e.response.json()
            return {'error': str(e)}
    
    def get_accounts(self) -> Dict[str, Any]:
        """Get all accounts."""
        return self._request('GET', '/api/v3/brokerage/accounts')
    
    def get_orders(self, order_status: str = 'OPEN') -> Dict[str, Any]:
        """Get orders by status."""
        return self._request('GET', f'/api/v3/brokerage/orders/batch?order_status={order_status}')
    
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
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'BUY',
                'order_configuration': {
                    'market_market_ioc': {
                        'base_size': f"{qty:.8f}"
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
            body = {
                'client_order_id': secrets.token_hex(16),
                'product_id': product_id,
                'side': 'BUY',
                'order_configuration': {
                    'limit_limit_gtc': {
                        'base_size': f"{qty:.8f}",
                        'limit_price': f"{price:.2f}"
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
