"""
Phase 6 Exchange Client (Shadow + Live capable)

Unified interface for Phase 6.
- Shadow: realistic simulation for testing
- Live: delegates to real Coinbase Advanced Trade via CoinbaseWrapper
"""

from typing import Dict, Any, Optional, List
import os
import time
import logging
import secrets

logger = logging.getLogger(__name__)

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

    def __init__(self, mode: str = "shadow", initial_capital: float = 1000.0):
        self.mode = mode.lower()
        self.shadow_mode = (self.mode == "shadow")
        self._balances = {"USD": initial_capital}
        self._positions: Dict[str, float] = {}
        self._order_log = []
        self.real_client = None

        if not self.shadow_mode:
            self._init_live_client()

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

        if self.real_client:
            try:
                accounts = self.real_client.get_accounts()
                for acc in accounts.get("accounts", []):
                    if acc.get("currency") == currency:
                        return float(acc.get("available_balance", {}).get("value", 0.0))
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
                    price = float(data["data"]["amount"])
                    return round(price, 2)
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
            print("[LIVE] Real client not available for stop-limit")
            return False

        try:
            limit_p = limit_price or round(stop_price * 0.995, 2)

            body = {
                "client_order_id": secrets.token_hex(16),
                "product_id": product_id,
                "side": "SELL",
                "order_configuration": {
                    "stop_limit_stop_limit_gtc": {
                        "base_size": str(qty),
                        "limit_price": str(limit_p),
                        "stop_price": str(stop_price)
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
        More robust parsing to capture positions even when they are in 'hold'.
        """
        if self.shadow_mode:
            return self._positions.copy()

        holdings = {}
        if not self.real_client:
            return holdings
        try:
            accounts = self.real_client.get_accounts()
            for acc in accounts.get("accounts", []):
                currency = acc.get("currency", "")
                if currency and currency != "USD":
                    # Check both available_balance and hold
                    available = float(acc.get("available_balance", {}).get("value", 0.0))
                    hold = float(acc.get("hold", {}).get("value", 0.0))
                    total = available + hold

                    if total > 0:
                        holdings[currency] = total
            return holdings
        except Exception as e:
            logger.error(f"Failed to fetch live holdings: {e}")
            return {}
        # Fallback if no real_client
        return {}

    def get_open_orders(self, product_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open orders, optionally filtered by product. Placeholder for live.
        In live would query /api/v3/brokerage/orders?status=OPEN
        """
        if self.shadow_mode:
            # In shadow, we don't track open orders yet; return []
            return []
        # Live stub - prevents crash, real impl would delegate
        logger.info(f"[LIVE] get_open_orders called for {product_id or 'all'} (stub)")
        return []


    
    def get_recent_prices(self, product_id: str, limit: int = 20, granularity: str = "ONE_HOUR") -> list[float]:
        """Fetch recent historical candle closes using the public Coinbase endpoint.
        Rate limit aware: public endpoint should not be called too frequently.
        """
        # Simple in-memory cache to avoid hammering the public API
        cache_key = f"{product_id}:{limit}:{granularity}"
        if not hasattr(self, "_price_cache"):
            self._price_cache = {}
        if cache_key in self._price_cache:
            cached_time, cached_data = self._price_cache[cache_key]
            if (datetime.now() - cached_time).seconds < 300:  # 5 min cache
                return cached_data

        try:
            import requests
            from datetime import datetime, timedelta, timezone

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
            self._price_cache[cache_key] = (datetime.now(), result)
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
        """
        holdings = self.get_holdings()
        if not holdings:
            return {}

        enriched = {}
        for currency, amount in holdings.items():
            pair = f"{currency}-USD"
            try:
                price = price_snapshot.get(pair) if price_snapshot else self.get_price(pair)

                if price and price > 0:
                    value_usd = round(amount * price, 2)
                    enriched[currency] = {
                        "amount": amount,
                        "current_price": price,
                        "value_usd": value_usd,
                        "entry_price": 0.0,             # Unknown - do not use current price
                        "unrealized_pnl_pct": 0.0,      # Requires real entry price
                        "side": "long"
                    }
            except Exception as e:
                logger.warning(f"Failed to enrich {currency}: {e}")
                continue
        return enriched

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order by ID. Placeholder.
        """
    def get_open_orders(self, pair: str = None) -> list:
        """Return list of open orders. Works in both shadow and live mode."""
        if self.shadow_mode:
            return []
        if not self.real_client:
            return []
        try:
            resp = self.real_client._request(
                "GET", 
                "/api/v3/brokerage/orders/historical/batch",
                params={"order_status": "OPEN"}
            )
            orders = resp.get("orders", []) if isinstance(resp, dict) else []
            if pair:
                orders = [o for o in orders if o.get("product_id") == pair]
            return orders
        except Exception as e:
            logger.warning(f"get_open_orders failed: {e}")
            return []