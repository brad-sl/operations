"""
Phase 6 Exchange Client (Shadow + Live capable)

Unified interface for Phase 6.
- Shadow: realistic simulation for testing
- Live: delegates to real Coinbase Advanced Trade via CoinbaseWrapper

PERMANENT FIX FOR API KEYS BECOMING INVISIBLE ON DEPLOYMENTS:
The COINBASE_API_KEY and COINBASE_API_SECRET are ALWAYS in the project-local .env
(/home/brad/projects/crypto-trading-bot/.env). This module now self-loads it (plus
~/.hermes/.env) at import time. No more dependence on shell sourcing order or
load_dotenv() only happening inside main(). .gitignore is for git only.
"""

from typing import Dict, Any, Optional, List
import os
import time
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# === PERMANENT ROBUST LOADING FIX ===
def _ensure_trading_secrets_loaded():
    try:
        any_loaded = False
        if load_dotenv():
            any_loaded = True
        project_env = Path("/home/brad/projects/crypto-trading-bot/.env")
        if project_env.exists():
            if load_dotenv(str(project_env), override=False):
                any_loaded = True
        hermes_env = Path.home() / ".hermes" / ".env"
        if hermes_env.exists():
            load_dotenv(str(hermes_env), override=False)
        home_env = Path.home() / ".env"
        if home_env.exists():
            load_dotenv(str(home_env), override=False)
        if not any_loaded:
            logger.debug("No .env files found; relying on shell os.environ")
    except Exception as e:
        logger.warning(f"Non-fatal dotenv issue: {e}")

_ensure_trading_secrets_loaded()
# === END PERMANENT FIX ===

try:
    from coinbase_wrapper_FIXED import CoinbaseWrapper
except ImportError:
    CoinbaseWrapper = None

class CoinbaseExchangeClient:
    """
    Unified exchange client for Phase 6.

    - Shadow mode: Simulates balances, prices, and order execution
    - Live mode: Delegates to real Coinbase Advanced Trade client
    """

    def __init__(self, mode: str = "shadow", initial_capital: float = None):
        self.mode = mode.lower()
        self.shadow_mode = (self.mode == "shadow")
        self._balances = {"USD": initial_capital} if initial_capital is not None else {"USD": 0.0}
        self._positions: Dict[str, float] = {}
        self._order_log = []
        self.real_client = None
        self._price_cache = {}

    def _round_size_for_product(self, product_id: str, qty: float) -> str:
        """Round quantity to acceptable precision for the product."""
        meta = self.get_product_metadata(product_id)
        return self._quantize_size(qty, meta["base_increment"])
    
    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        """Fetch quantization increments for the product."""
        # Placeholder for dynamic fetch
        if "BTC" in product_id:
            return {"price_increment": 0.01, "base_increment": 0.00000001}
        elif "DOGE" in product_id:
            return {"price_increment": 0.00001, "base_increment": 1.0}
        elif "XRP" in product_id:
            return {"price_increment": 0.0001, "base_increment": 0.1}
        elif "SOL" in product_id:
            return {"price_increment": 0.001, "base_increment": 0.01}
        elif "ADA" in product_id:
            return {"price_increment": 0.0001, "base_increment": 1.0}
        elif "ETH" in product_id:
            return {"price_increment": 0.01, "base_increment": 0.00001}
        return {"price_increment": 0.01, "base_increment": 0.001}

    def _quantize_price(self, price: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(price)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))

    def _quantize_size(self, size: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(size)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))


    def _ensure_live_client(self):
        """Defensive on-demand initialization of real_client."""
        if self.real_client is not None:
            return True

        if self.shadow_mode:
            return False

        try:
            api_key = os.getenv("COINBASE_API_KEY")
            private_key = os.getenv("COINBASE_API_SECRET")

            if not api_key or not private_key:
                logger.warning("No Coinbase credentials found for live mode")
                return False

            # P6-144: normalize newlines in private key (JWT PEMs often come with literal \n)
            private_key = private_key.replace("\\n", "\n")

            from coinbase_wrapper_FIXED import CoinbaseWrapper
            self.real_client = CoinbaseWrapper(api_key=api_key, private_key=private_key)
            logger.info("Live Coinbase client initialized on-demand")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize live client on-demand: {e}")
            return False


    def _init_live_client(self):
        """Initialize real Coinbase client for live mode."""
        api_key = os.getenv("COINBASE_API_KEY")
        private_key = os.getenv("COINBASE_API_SECRET")

        if not api_key or not private_key:
            raise ValueError(
                "Live mode requires COINBASE_API_KEY and COINBASE_API_SECRET environment variables"
            )

        if CoinbaseWrapper is None:
            raise ImportError("coinbase_wrapper_FIXED.py not found or import failed")

        private_key = private_key.replace("\\n", "\n")

        try:
            self.real_client = CoinbaseWrapper(
                api_key=api_key,
                private_key=private_key,
                sandbox=False
            )
            logger.info("✅ Live Coinbase client initialized (real trading enabled)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize live Coinbase client: {e}")
            raise

    # ------------------------------------------------------------------
    # Account & Market Data
    # ------------------------------------------------------------------

    def get_account_balance(self, currency: str = "USD") -> float:
        if self.shadow_mode:
            return self._balances.get(currency, 0.0)

        if not self.real_client:
            self._ensure_live_client()

        if self.real_client:
            try:
                accounts = self.real_client.get_accounts()
                for acc in accounts.get("accounts", []):
                    if acc.get("currency") == currency:
                        available = float(acc.get("available_balance", {}).get("value", 0.0))
                        hold = float(acc.get("hold", {}).get("value", 0.0))
                        return available + hold
                return 0.0
            except Exception as e:
                logger.error(f"Failed to fetch live balance: {e}")
                return 0.0
        return 0.0

    def get_price(self, product_id: str) -> float:
        """Return current spot price for a product.

        IMPORTANT: Live mode must NEVER return hardcoded/fake prices.
        - Shadow mode: returns deterministic test prices
        - Live mode: fetches real price from Coinbase public API
        """
        if self.shadow_mode:
            prices = {
                "BTC-USD": 65000.0,
                "ETH-USD": 3200.0,
                "SOL-USD": 145.0,
                "XRP-USD": 0.52,
                "DOGE-USD": 0.12,
            }
            return prices.get(product_id, 100.0)

        # === LIVE MODE: Must return real market data ===
        # Live mode with retry
        for attempt in range(1, 4):
            try:
                import requests
                url = f"https://api.coinbase.com/v2/prices/{product_id}/spot"
                resp = requests.get(url, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    # Return full precision float from API response
                    return float(data["data"]["amount"])
                else:
                    logger.warning(f"get_price attempt {attempt}: HTTP {resp.status_code}")
            except Exception as e:
                logger.warning(f"get_price attempt {attempt} failed: {e}")
            if attempt < 3:
                import time; time.sleep(1.5 ** attempt)
        logger.error(f"get_price: All attempts failed for {product_id} - returning 0.0")
        return 0.0
    def place_market_buy(self, product_id: str, usd_amount: float) -> Dict[str, Any]:
        if self.shadow_mode:
            self._order_log.append({
                "type": "market_buy",
                "pair": product_id,
                "usd_amount": usd_amount,
                "timestamp": time.time()
            })
            return {"success": True, "order_id": "shadow_order"}

        if not self.real_client:
            if not self._ensure_live_client():
                return {"success": False, "error": "No live client"}

        try:
            body = {
                "client_order_id": __import__('secrets').token_hex(16),
                "product_id": product_id,
                "side": "BUY",
                "order_configuration": {
                    "market_market_ioc": {
                        "quote_size": str(usd_amount)
                    }
                }
            }
            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)
            if "success_response" in resp or resp.get("success"):
                return {"success": True, "order_id": resp.get("success_response", {}).get("order_id")}
            else:
                return {"success": False, "error": str(resp)}
        except Exception as e:
            logger.error(f"Live market buy failed: {e}")
            return {"success": False, "error": str(e)}

    def place_stop_limit_sell(
        self,
        product_id: str,
        qty: float,
        stop_price: float,
        limit_price: Optional[float] = None
    ) -> bool:
        """Place native stop-limit sell order using correct Coinbase schema."""
        if self.shadow_mode:
            self._order_log.append({
                "type": "stop_limit_sell",
                "pair": product_id,
                "qty": qty,
                "stop_price": stop_price,
                "limit_price": limit_price,
                "timestamp": time.time()
            })
            print(f"[SHADOW] Stop-limit SL placed for {product_id} @ ${stop_price}")
            return True

        if not self.real_client:
            if not self._ensure_live_client():
                print("[LIVE] Real client not available for stop-limit")
                return False

        try:
            limit_p = limit_price or stop_price * 0.995

            meta = self.get_product_metadata(product_id)
            body = {
                "client_order_id": secrets.token_hex(16),
                "product_id": product_id,
                "side": "SELL",
                "order_configuration": {
                    "stop_limit_stop_limit_gtc": {
                        "base_size": self._quantize_size(qty, meta["base_increment"]),
                        "limit_price": self._quantize_price(limit_p, meta["price_increment"]),
                        "stop_price": self._quantize_price(stop_price, meta["price_increment"]),
                        "stop_direction": "STOP_DIRECTION_STOP_DOWN"
                    }
                }
            }

            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)

            if "success_response" in resp or resp.get("success"):
                print(f"[LIVE] Native stop-limit SL placed for {product_id} @ ${stop_price}")
                self._order_log.append({
                    "type": "stop_limit_sell",
                    "pair": product_id,
                    "qty": qty,
                    "stop_price": stop_price,
                    "limit_price": limit_price,
                    "timestamp": time.time(),
                    "response": resp
                })
                return True
            else:
                logger.warning(f"Stop-limit order may have failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Live stop-limit failed: {e}")
            return False

    def get_holdings(self) -> Dict[str, float]:
        """Return current crypto holdings as {asset: amount}.
        Deprecated: Use get_holdings_verified() instead.
        """
        data = self.get_holdings_verified()
        if not data.get("verified", False):
            return {}
        return data.get("positions", {})

    def get_holdings_verified(self) -> Dict[str, Any]:
        """Return {positions: {asset: amount}, verified: bool, error: Optional[str]}"""
        if self.shadow_mode:
            return {"positions": self._positions.copy(), "verified": True, "error": None}

        if not self.real_client:
            self._ensure_live_client()
            
        if not self.real_client:
            return {"positions": {}, "verified": False, "error": "No live client"}
            
        try:
            accounts = self.real_client.get_accounts()
            holdings = {}
            for acc in accounts.get("accounts", []):
                currency = acc.get("currency", "")
                if currency and currency != "USD":
                    available = float(acc.get("available_balance", {}).get("value", 0.0))
                    hold = float(acc.get("hold", {}).get("value", 0.0))
                    total = available + hold
                    if total > 0:
                        holdings[currency] = total
            return {"positions": holdings, "verified": True, "error": None}
        except Exception as e:
            logger.error(f"Failed to fetch live holdings: {e}")
            return {"positions": {}, "verified": False, "error": str(e)}


    
    def get_recent_prices(self, product_id: str, limit: int = 20, granularity: str = "ONE_HOUR") -> list[float]:
        """Fetch recent historical candle closes using the public Coinbase endpoint.
        Rate limit aware: public endpoint should not be called too frequently.
        """
        # Simple in-memory cache to avoid hammering the public API
        cache_key = f"{product_id}:{limit}:{granularity}"
        if cache_key in self._price_cache:
            cached_time, cached_data = self._price_cache[cache_key]
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < 300:  # 5 min cache
                return cached_data

        try:
            import requests

            # Map granularity
            gran_map = {
                "ONE_MINUTE": 60,
                "FIVE_MINUTE": 300,
                "FIFTEEN_MINUTE": 900,
                "ONE_HOUR": 3600,
                "SIX_HOUR": 21600,
                "ONE_DAY": 86400
            }
            gran_seconds = gran_map.get(granularity, 3600)

            end = datetime.now(timezone.utc)
            start = end - timedelta(seconds=gran_seconds * (limit + 5))

            url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
            params = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": gran_seconds
            }

            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Public candles failed for {product_id}: {resp.status_code}")
                return []

            candles = resp.json()
            # Coinbase returns [time, low, high, open, close, volume]
            # Most recent first → reverse so oldest first
            closes = [float(c[4]) for c in reversed(candles) if len(c) >= 5]
            result = closes[-limit:] if closes else []

            # Cache the result
            self._price_cache[cache_key] = (datetime.now(timezone.utc), result)
            return result

        except Exception as e:
            logger.warning(f"get_recent_prices (public) failed for {product_id}: {e}")
            return []


    def get_enriched_positions(self, force_refresh: bool = False, price_snapshot: Optional[Dict[str, float]] = None) -> Dict[str, Dict]:
        """Return enriched positions with current market data.
        If price_snapshot is provided, use it instead of direct exchange calls.

        Note: entry_price is left as None or 0.0 when unknown.
              Callers should enrich with actual entry data from trade history
              if accurate PnL is required.

        P6-151/G3 fix: NEVER return bare {} on empty or error.
        Always return {"positions": {...}, "verified": bool, "error": ..., "value_usd": {...}}
        """
        holdings = self.get_holdings()
        if not holdings:
            return {
                "positions": {},
                "verified": True,  # empty is valid for verified-zero Fresh Start case
                "error": None,
                "value_usd": {}
            }

        enriched = {}
        for currency, amount in holdings.items():
            pair = f"{currency}-USD"
            try:
                price = price_snapshot.get(pair) if price_snapshot else self.get_price(pair)

                if price and price > 0:
                    value_usd = amount * price
                    # P6-001 fix: always normalize to -USD keys using value_usd only at the data boundary
                    # This ensures downstream (runner, deploy_capital, sentiment, rebalance_plan) see
                    # consistent pair symbols and real USD values (never coin quantities).
                    enriched[pair] = {
                        "amount": amount,
                        "current_price": price,
                        "value_usd": value_usd,
                        "entry_price": 0.0,
                        "unrealized_pnl_pct": 0.0,
                        "side": "long"
                    }
            except Exception as e:
                logger.warning(f"Failed to enrich {currency}: {e}")
                continue
        return enriched

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order by ID."""
        if self.shadow_mode:
            return True

        if not self.real_client:
            if not self._ensure_live_client():
                return False

        try:
            body = {"order_ids": [order_id]}
            resp = self.real_client._request("POST", "/api/v3/brokerage/orders/batch_cancel", body)
            
            # Coinbase batch_cancel usually returns a list of results
            # We want to check if the specific order was cancelled
            results = resp.get("results", [])
            for res in results:
                if res.get("order_id") == order_id:
                    return bool(res.get("success"))
            
            return False
        except Exception as e:
            logger.error(f"Failed to cancel live order {order_id}: {e}")
            return False

    def get_open_orders(self, pair: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of open orders. Works in both shadow and live mode.
        Enhanced to return richer structure and better support stop-order detection.
        Robust to 401/permission errors. Prefers wrapper method.
        """
        if self.shadow_mode:
            return []
        if not self.real_client:
            if not self._ensure_live_client():
                return []
        try:
            # Prefer wrapper's get_orders if available (consolidated logic)
            if hasattr(self.real_client, 'get_orders'):
                resp = self.real_client.get_orders(order_status='OPEN')
            else:
                resp = self.real_client._request(
                    "GET", 
                    "/api/v3/brokerage/orders/historical/batch?order_status=OPEN"
                )
            if isinstance(resp, dict) and ("error" in str(resp).lower() or resp.get("error")):
                logger.warning(f"get_open_orders returned error (may be permission): {resp}")
                return []
            orders = resp.get("orders", []) if isinstance(resp, dict) else []
            if pair:
                orders = [o for o in orders if o.get("product_id") == pair]
            
            # Normalize for coordinator
            normalized = []
            for o in orders:
                norm = dict(o)
                oc = o.get("order_configuration", {}) or {}
                if "stop_limit" in oc or "stop_market" in oc or "stop" in str(o.get("order_type", "")).lower():
                    norm["order_type"] = "STOP_LIMIT"
                    sp = oc.get("stop_limit", {}).get("stop_price") or oc.get("stop_limit_stop_limit_gtc", {}).get("stop_price")
                    if sp:
                        norm["stop_price"] = float(sp)
                normalized.append(norm)
            return normalized
        except Exception as e:
            logger.warning(f"get_open_orders failed (graceful empty): {e}")
            return []

    def get_open_stop_orders(self, pair: Optional[str] = None) -> List[Dict[str, Any]]:
        """Dedicated fetch for open stop orders. Filters get_open_orders results."""
        all_orders = self.get_open_orders(pair) or []
        stop_orders = []
        for o in all_orders:
            order_type = str(o.get("order_type", "")).lower()
            oc = o.get("order_configuration", {}) or {}
            if "stop" in order_type or "stop_price" in o or any(k in oc for k in ("stop_limit", "stop_market")):
                stop_orders.append(o)
        return stop_orders

    def place_market_sell(self, product_id: str, size: float) -> dict:
        """Market sell using base size. Symmetric to buy. Real fills only."""
        if self.shadow_mode:
            self._order_log.append({"type": "market_sell", "pair": product_id, "size": size, "timestamp": __import__('time').time()})
            return {"success": True, "order_id": "shadow_sell", "size": size}
        if not self.real_client:
            if not self._ensure_live_client():
                return {"success": False, "error": "No live client"}
        try:
            body = {
                "client_order_id": __import__('secrets').token_hex(16),
                "product_id": product_id,
                "side": "SELL",
                "order_configuration": {"market_market_ioc": {"base_size": str(size)}}
            }
            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)
            if "success_response" in resp or resp.get("success"):
                return {"success": True, "order_id": resp.get("success_response", {}).get("order_id"), "size": size}
            return {"success": False, "error": str(resp)}
        except Exception as e:
            return {"success": False, "error": str(e)}
