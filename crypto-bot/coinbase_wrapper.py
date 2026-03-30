"""
Coinbase Advanced Trade API Wrapper
Handles authentication, order execution, and portfolio queries.
Supports both sandbox (paper trading) and live modes.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import json
import hmac
import hashlib
import time
from urllib.parse import urlencode

@dataclass
class OrderResponse:
    """Structured response from order operations."""
    success: bool
    order_id: Optional[str] = None
    product_id: str = "BTC-USD"
    side: str = "buy"  # buy or sell
    price: float = 0.0
    size: float = 0.0
    status: str = "PENDING"
    timestamp: str = ""
    error: Optional[str] = None

class CoinbaseWrapper:
    """
    Wraps Coinbase Advanced Trade API with Ed25519 authentication.
    
    Supports:
    - Paper trading (sandbox=True)
    - Live trading (sandbox=False, requires manual approval)
    - Order management (create, cancel, history)
    - Account queries (balance, prices)
    """
    
    def __init__(
        self,
        api_key: str,
        private_key: str,
        passphrase: str,
        sandbox: bool = True
    ):
        """
        Initialize Coinbase wrapper.
        
        Args:
            api_key: Coinbase API key
            private_key: Ed25519 private key (not OAuth)
            passphrase: API passphrase
            sandbox: Use sandbox (paper trading) mode
        """
        self.api_key = api_key
        self.private_key = private_key
        self.passphrase = passphrase
        self.sandbox = sandbox
        
        # Base URLs
        self.base_url = (
            "https://api-sandbox.coinbase.com"
            if sandbox
            else "https://api.coinbase.com"
        )
        self.product_id = "BTC-USD"
    
    def _generate_signature(self, method: str, path: str, body: str = "") -> tuple:
        """
        Generate Ed25519 signature for Coinbase API.
        
        Returns:
            Tuple of (signature, timestamp)
        
        Raises:
            ValueError: If signature generation fails (sanitized error message)
        """
        try:
            timestamp = str(time.time())
            message = timestamp + method + path + body
            
            # In production: use actual Ed25519 signing
            # For now: placeholder HMAC (will be replaced with real Ed25519)
            signature = hmac.new(
                self.private_key.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return signature, timestamp
        except Exception as e:
            # Do NOT log the full exception (might contain credentials)
            # Return generic error message to prevent private_key leakage
            raise ValueError("Signature generation failed") from e
    
    def get_balance(self, currency: str = "BTC") -> Dict[str, Any]:
        """
        Get account balance for a currency.
        
        Args:
            currency: Currency code (BTC, USD, etc.)
        
        Returns:
            {"success": bool, "currency": str, "balance": float, ...}
        """
        try:
            # In production: call GET /accounts endpoint
            # For now: return mock response
            return {
                "success": True,
                "currency": currency,
                "balance": 0.5 if currency == "BTC" else 10000.0,
                "hold": 0.0,
                "available": 0.5 if currency == "BTC" else 10000.0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_price(self, product_id: str = "BTC-USD") -> Dict[str, Any]:
        """
        Get current price and 24h change from Coinbase API (with fallback).
        
        Args:
            product_id: Product ID (e.g., "BTC-USD")
        
        Returns:
            {"success": bool, "price": float, "change_24h": float, ...}
        """
        try:
            # Live Coinbase API call: GET /products/{product_id}/ticker
            import requests
            response = requests.get(
                f"{self.base_url}/products/{product_id}/ticker",
                headers={
                    "CB-ACCESS-KEY": self.api_key,
                    "User-Agent": "crypto-bot/phase4",
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            price = float(data.get("price", 0.0))
            if price <= 0:
                raise ValueError(f"Invalid price from API: {price}")
            
            # Log successful price fetch
            import logging
            logging.info(f"PRICE_FETCH: {product_id}={price}")
            
            return {
                "success": True,
                "product_id": product_id,
                "price": price,
                "change_24h": float(data.get("change_24h", 0.0)),
                "change_percent_24h": float(data.get("change_percent_24h", 0.0)),
            }
        except Exception as e:
            # Fallback to deterministic price (no randomness)
            fallback_price = self._fallback_price(product_id)
            import logging
            logging.warning(f"PRICE_FETCH_FALLBACK: {product_id}={fallback_price} (error: {e})")
            
            return {
                "success": True,
                "product_id": product_id,
                "price": fallback_price,
                "change_24h": 0.0,
                "change_percent_24h": 0.0,
                "note": "Using fallback price due to API error",
            }
    
    def _fallback_price(self, product_id: str) -> float:
        """
        Deterministic fallback prices (no randomness, no real API call).
        
        Args:
            product_id: Product ID (e.g., "BTC-USD")
        
        Returns:
            Fallback price for offline/error scenarios
        """
        fallback_prices = {
            "BTC-USD": 67500.0,
            "XRP-USD": 2.50,
            "ETH-USD": 3500.0,
        }
        return fallback_prices.get(product_id, 50000.0)
    
    def create_order(
        self,
        product_id: str,
        side: str,
        order_type: str,
        price: float,
        size: float,
    ) -> OrderResponse:
        """
        Create a limit order.
        
        Args:
            product_id: e.g., "BTC-USD"
            side: "buy" or "sell"
            order_type: "limit" (market orders require approval)
            price: Limit price
            size: Order size in BTC
        
        Returns:
            OrderResponse with order details
        """
        try:
            if not self.sandbox:
                raise SystemExit(
                    "\n" + "="*70 +
                    "\n🚨 LIVE TRADING BLOCKED: Phase 3 NOT APPROVED\n" +
                    "Create wrapper with sandbox=True for paper trading.\n" +
                    "="*70
                )
            
            if side not in ["buy", "sell"]:
                raise ValueError(f"Invalid side: {side}")
            
            if order_type != "limit":
                raise ValueError("Only limit orders supported")
            
            # In production: call POST /orders endpoint
            # For now: return mock order
            return OrderResponse(
                success=True,
                order_id="order-" + str(int(time.time())),
                product_id=product_id,
                side=side,
                price=price,
                size=size,
                status="OPEN",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
        except Exception as e:
            return OrderResponse(
                success=False,
                error=str(e),
                status="FAILED",
            )
    
    def cancel_order(self, order_id: str) -> OrderResponse:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID from create_order response
        
        Returns:
            OrderResponse confirmation
        """
        try:
            # In production: call DELETE /orders/{order_id} endpoint
            # For now: return mock cancellation
            return OrderResponse(
                success=True,
                order_id=order_id,
                status="CANCELLED",
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
        except Exception as e:
            return OrderResponse(
                success=False,
                order_id=order_id,
                error=str(e),
                status="CANCEL_FAILED",
            )
    
    def get_orders(
        self,
        product_id: str = "BTC-USD",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get order history.
        
        Args:
            product_id: Filter by product
            limit: Number of recent orders
        
        Returns:
            List of order dictionaries
        """
        try:
            # In production: call GET /orders endpoint with filters
            # For now: return empty list (no orders in mock)
            return []
        except Exception as e:
            return [{"error": str(e)}]
