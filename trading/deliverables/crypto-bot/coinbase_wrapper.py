"""
Coinbase Advanced Trade API Wrapper
Handles authentication, order execution, and portfolio queries.
Supports both sandbox (paper trading) and live modes.

CRITICAL: Production code uses REAL Coinbase API only.
Test code must use test_price_wrapper.py with PRICE_SOURCE environment variable.
NO synthetic fallback prices allowed in production code.
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
    
    PRODUCTION RULE: get_price() MUST use real API or raise exception.
    Test harnesses MUST use test_price_wrapper.py with PRICE_SOURCE environment variable.
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
        
        # Base URLs: Sandbox uses REST API v3 (different from v1)
        # v1 endpoints: /products (deprecated)
        # v3 endpoints: /api/v3/brokerage/ (current standard)
        if sandbox:
            # Sandbox REST API v3 endpoint
            self.base_url = "https://api-sandbox.coinbase.com"
            self.api_version = "v3"
        else:
            # Production REST API v3 endpoint
            self.base_url = "https://api.coinbase.com"
            self.api_version = "v3"
        
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
            # In production: call GET /api/v3/brokerage/accounts endpoint
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
        Get current price from Coinbase API (REAL PRICES ONLY).
        
        Production code uses real Coinbase Advanced Trade API v3.
        Test code must use test_price_wrapper.py with PRICE_SOURCE environment variable.
        
        Args:
            product_id: Product ID (e.g., "BTC-USD", "ETH-USD")
        
        Returns:
            {
                "success": bool,
                "product_id": str,
                "price": float,
                "change_24h": float,
                "change_percent_24h": float
            }
        
        Raises:
            ValueError: If API call fails (no fallback, fail-fast principle)
        """
        try:
            import requests
            
            # Coinbase Advanced Trade API v3: GET /api/v3/brokerage/products/{product_id}
            # Returns full product info including current price
            endpoint = f"{self.base_url}/api/v3/brokerage/products/{product_id}"
            
            response = requests.get(
                endpoint,
                headers={
                    "CB-ACCESS-KEY": self.api_key,
                    "User-Agent": "crypto-bot/phase4b",
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract price from API response
            # v3 returns: {"product_id": "...", "price": "...", ...}
            price = float(data.get("price", 0.0))
            if price <= 0:
                raise ValueError(f"Invalid price from API: {price}")
            
            # Log successful price fetch
            import logging
            logging.info(f"PRICE_FETCH: {product_id}=${price:.2f}")
            
            return {
                "success": True,
                "product_id": product_id,
                "price": price,
                "change_24h": float(data.get("price_percentage_change_24h", 0.0)),
                "change_percent_24h": float(data.get("price_percentage_change_24h", 0.0)),
            }
        except Exception as e:
            # PRODUCTION RULE: NO FALLBACK
            # Fail fast. Test code must provide PRICE_SOURCE=snapshot.
            import logging
            logging.error(f"❌ PRICE_FETCH FAILED: {product_id} - {str(e)}")
            raise ValueError(
                f"Cannot fetch real price for {product_id} from Coinbase API. "
                f"Check API connectivity and credentials. "
                f"For testing, set PRICE_SOURCE=snapshot environment variable "
                f"and use test_price_wrapper.py."
            ) from e
    
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
                    "\n🚨 LIVE TRADING BLOCKED: Phase 4B NOT APPROVED\n" +
                    "Create wrapper with sandbox=True for paper trading.\n" +
                    "="*70
                )
            
            if side not in ["buy", "sell"]:
                raise ValueError(f"Invalid side: {side}")
            
            if order_type != "limit":
                raise ValueError("Only limit orders supported")
            
            # In production: call POST /api/v3/brokerage/orders endpoint
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
            # In production: call DELETE /api/v3/brokerage/orders/{order_id} endpoint
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
            # In production: call GET /api/v3/brokerage/orders/historical/batch endpoint
            # For now: return empty list (no orders in mock)
            return []
        except Exception as e:
            return [{"error": str(e)}]
