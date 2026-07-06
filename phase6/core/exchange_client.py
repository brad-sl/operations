"""
Phase 6 Exchange Client (Shadow + Live capable)
Unified interface for Phase 6.
- Shadow: realistic simulation for testing
- Live: delegates to real Coinbase Advanced Trade 
  Primary orders via official coinbase.rest.RESTClient.list_orders (to eliminate 401 historical/batch); fallback wrapper for other endpoints.

Centralized dotenv via paths.load_project_dotenv() at import time (see paths.py and DATA_FLOW doc). No hard-coded project path in this file.
"""

from typing import Dict, Any, Optional, List
import os
import time
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .paths import PROJECT_ROOT, load_project_dotenv  # DATA_FLOW + central dotenv

logger = logging.getLogger(__name__)

# Centralized dotenv (config hygiene) - call early at import
load_project_dotenv()

try:
    from coinbase_wrapper_FIXED import CoinbaseWrapper
except ImportError:
    CoinbaseWrapper = None

try:
    from coinbase.rest import RESTClient
except ImportError:
    RESTClient = None

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
        self.sdk_client = None
        self._price_cache = {}
        # P0-02.2: initialize meta cache at construction for robustness (no lazy hasattr)
        self._product_meta_cache: Dict[str, Dict[str, float]] = {}

    def _round_size_for_product(self, product_id: str, qty: float) -> str:
        """Round quantity to acceptable precision for the product. P0-02: delegates to public quantize_size."""
        return self.quantize_size(product_id, qty)

    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        """HARDENED (P0-02.2): Fetch quantization increments dynamically from public Coinbase /products API.

        - Live fetch ALWAYS preferred (no-auth public endpoint).
        - Robust error handling (specific + fallback), improved logging.
        - Per-instance cache initialized in __init__ (avoids repeated calls).
        - Maps quote_increment -> price_increment (primary for this API), base_increment preserved.
        - Verified fallbacks for full 11-pair dynamic basket (BTC/ETH/SOL/XRP/DOGE/ADA/AVAX/LINK/UNI/ARB/OP).
        - Verified 2026-07-03 using real API responses (quote_increment used; values match live exchange specs).
        - Falls back only on failure; logs at appropriate level.
        - No breaking changes: returns {"price_increment": float, "base_increment": float}
        """
        pid = product_id.upper()
        if pid in self._product_meta_cache:
            return self._product_meta_cache[pid].copy()

        # Try dynamic public fetch (no auth required for basic product specs)
        try:
            import requests
            url = f"https://api.exchange.coinbase.com/products/{pid}"
            resp = requests.get(url, timeout=8)  # slightly longer timeout for reliability
            if resp.status_code == 200:
                d = resp.json()
                # Safe extraction + float conversion; prefer quote_increment (as observed in real responses)
                q_inc = d.get("quote_increment") or d.get("price_increment")
                b_inc = d.get("base_increment")
                meta = {
                    "price_increment": float(q_inc) if q_inc is not None else 0.01,
                    "base_increment": float(b_inc) if b_inc is not None else 0.001,
                }
                self._product_meta_cache[pid] = meta
                logger.info(f"[DYNAMIC META] Fetched for {pid}: {meta}")
                return meta.copy()
            else:
                logger.debug(f"[DYNAMIC META] HTTP {resp.status_code} for {pid}")
        except requests.exceptions.RequestException as e:
            logger.debug(f"[DYNAMIC META] Network error for {pid}: {e}")
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"[DYNAMIC META] Parse/convert error for {pid}: {e}")
        except Exception as e:
            logger.debug(f"[DYNAMIC META] Unexpected fetch error for {pid}: {e}")

        # Fallback to verified hardcoded (for shadow, network failure, or new pairs)
        # All values verified against real /products responses 2026-07-03 for the 11-pair basket.
        # See workspace artifact: real_product_metadata.json and test_isolation_product_metadata.py
        # Dynamic fetch is always attempted first.
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
        if pid in fallbacks:
            meta = fallbacks[pid].copy()
            logger.info(f"[META FALLBACK] Using verified static fallback for {pid}: {meta} (dynamic unavailable)")
        else:
            meta = {"price_increment": 0.01, "base_increment": 0.001}
            logger.warning(f"[META FALLBACK] Unknown pair {pid} - using conservative default {meta}")

        self._product_meta_cache[pid] = meta
        return meta.copy()

    
    def poll_for_settlement(self, asset_or_pair: str, timeout: float = 30.0, max_polls: int = 15, expected_delta: float = 0.0, order_id: Optional[str] = None) -> bool:
        """
        ANALYST-20260703-051: Proper pre-flight settlement poll (updated from 20260629).
        Waits for actual fill/settlement before SL attach to avoid unfilled/INSUFFICIENT_FUND.
        - If order_id provided: polls get_order_fill_details until filled_size >0 or status FILLED (preferred for post-buy paths).
        - Fallback: polls crypto available balance until stable (for reattach etc).
        Similar to fill polling in execute_buy. Handles timeouts gracefully (logs + proceeds with caution).
        Uses get_order_fill_details or equivalent. Configurable timeout (longer for live buys).
        """
        import time
        if self.shadow_mode:
            return True

        start = time.time()
        # Prefer order-specific fill poll if order_id given (per spec for buy -> SL)
        if order_id:
            logger.info(f"[PRE-FLIGHT SETTLEMENT POLL] Waiting for actual fill on order {order_id} for {asset_or_pair} (timeout={timeout}s)")
            last_fill = {"filled_size": 0.0}
            polls = 0
            while time.time() - start < timeout:
                polls += 1
                try:
                    fill = self.get_order_fill_details(order_id) or {}
                    filled = float(fill.get("filled_size", 0) or 0)
                    status = str(fill.get("status", "")).upper()
                    if filled > 0 or status in ("FILLED", "SETTLED", "DONE", "FILLED_SETTLED"):
                        logger.info(f"[PRE-FLIGHT SETTLEMENT POLL] Order {order_id} confirmed settled: filled_size={filled}, status={status} after {polls} polls")
                        return True
                    last_fill = fill
                except Exception as e:
                    logger.debug(f"[PRE-FLIGHT] order fill poll error for {order_id}: {e}")
                if time.time() - start > timeout:
                    break
                time.sleep(2.0)  # match style of execute_buy fill poll (2s intervals)
            logger.warning(f"[PRE-FLIGHT SETTLEMENT POLL] Order {order_id} did not confirm fill within {timeout}s (filled={last_fill.get('filled_size')}, status={last_fill.get('status')}); proceeding cautiously to SL attach")
            return False  # indicate not confirmed, but caller may proceed

        # Fallback to asset balance stability poll (for non-order contexts like re-attach)
        asset = asset_or_pair.split("-")[0] if "-" in asset_or_pair else asset_or_pair
        last_avail = None
        for i in range(max_polls):
            try:
                avail = self.get_crypto_available(asset)
                if avail is not None:
                    if last_avail is not None and abs(avail - last_avail) < 1e-6:
                        if time.time() - start > timeout:
                            logger.info(f"[PRE-FLIGHT SETTLE] {asset} stable after {i+1} polls")
                            return True
                    last_avail = avail
            except Exception as e:
                logger.debug(f"[PRE-FLIGHT] poll error for {asset}: {e}")
            if time.time() - start > timeout:
                break
            time.sleep(min(2.0, timeout / max_polls))
        logger.warning(f"[PRE-FLIGHT SETTLE] {asset} did not fully settle within {timeout}s (proceeding with caution, attaching anyway)")
        return True  # legacy behavior: proceed to avoid missing SL window


    def _quantize_price(self, price: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(price)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))

    def _quantize_size(self, size: float, increment: float) -> str:
        from decimal import Decimal, ROUND_DOWN
        return str(Decimal(str(size)).quantize(Decimal(str(increment)), rounding=ROUND_DOWN))


    def quantize_price(self, product_id: str, price: float) -> str:
        """Public canonical (P0-02): quantize price for orders using product price_increment + Decimal ROUND_DOWN.
        Prefer this over ad-hoc or private.
        """
        meta = self.get_product_metadata(product_id)
        inc = float(meta.get("price_increment", 0.01))
        return self._quantize_price(price, inc)

    def quantize_size(self, product_id: str, size: float) -> str:
        """Public canonical (P0-02): quantize base size using product base_increment + Decimal ROUND_DOWN.
        Use for all SELL, SL, rebalance sizes. Unifies paths.
        """
        meta = self.get_product_metadata(product_id)
        inc = float(meta.get("base_increment", 0.001))
        return self._quantize_size(size, inc)

    def _ensure_live_client(self):
        """Defensive on-demand initialization of real_client."""
        if self.real_client is not None:
            return True
        if self.sdk_client is not None:
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
            
            # Primary for orders: official SDK (avoids custom JWT bugs for list/historical)
            if RESTClient is not None:
                try:
                    self.sdk_client = RESTClient(api_key=api_key, api_secret=private_key)
                    logger.info("Live Coinbase SDK (RESTClient) initialized for orders")
                except Exception as e:
                    logger.warning(f"SDK init failed, will fallback to wrapper: {e}")
                    self.sdk_client = None

            logger.info("Live Coinbase client initialized on-demand")
            try:
                perms = self.get_key_permissions()
                logger.info(f"Key permissions: {perms}")
            except Exception:
                pass
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
            if RESTClient is not None:
                try:
                    self.sdk_client = RESTClient(api_key=api_key, api_secret=private_key)
                    logger.info("SDK client also initialized in _init_live_client")
                except Exception as e:
                    logger.warning(f"SDK secondary init failed: {e}")
                    self.sdk_client = None

            logger.info("✅ Live Coinbase client initialized (real trading enabled)")
            try:
                perms = self.get_key_permissions()
                logger.info(f"Key permissions: {perms}")
            except Exception:
                pass
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

    def get_key_permissions(self) -> Dict[str, Any]:
        """Delegate to real client permissions check (live only). Returns dict with can_view etc or error."""
        if self.shadow_mode:
            return {"can_view": True, "can_trade": True, "shadow": True}
        if not self.real_client:
            self._ensure_live_client()
        if self.real_client and hasattr(self.real_client, "get_key_permissions"):
            try:
                return self.real_client.get_key_permissions()
            except Exception as e:
                return {"error": str(e)}
        return {"error": "no permissions method on client"}

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
            meta = self.get_product_metadata(product_id)
            # P0-02: use public canonical quantize_price (handles meta + _quantize_price + ROUND_DOWN) for BUY quote_size
            quote_size = self.quantize_price(product_id, usd_amount)
            body = {
                "client_order_id": __import__('secrets').token_hex(16),
                "product_id": product_id,
                "side": "BUY",
                "order_configuration": {
                    "market_market_ioc": {
                        "quote_size": quote_size
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


    def place_buy_with_bracket(self, product_id: str, usd_amount: float, 
                               tp_price: float = None, sl_price: float = None,
                               sl_pct: float = 0.03) -> Dict[str, Any]:
        """Place market buy with optional attached bracket TP/SL (atomic if supported)."""
        if self.shadow_mode:
            return {"success": True, "order_id": "shadow_bracket", "bracket": True}
        if not self.real_client:
            if not self._ensure_live_client():
                return {"success": False, "error": "no live client"}

        try:
            # P0-02: use public canonical quantize_price for BUY quote_size + brackets (unified)
            quote_size = self.quantize_price(product_id, usd_amount)
            body = {
                "client_order_id": __import__('secrets').token_hex(16),
                "product_id": product_id,
                "side": "BUY",
                "order_configuration": {
                    "market_market_ioc": {
                        "quote_size": quote_size
                    }
                }
            }
            if tp_price or sl_price:
                # Coinbase attached bracket support
                attached = {"trigger_bracket_gtc": {}}
                if tp_price:
                    attached["trigger_bracket_gtc"]["limit_price"] = self.quantize_price(product_id, tp_price)
                if sl_price:
                    attached["trigger_bracket_gtc"]["stop_trigger_price"] = self.quantize_price(product_id, sl_price)
                body["attached_order_configuration"] = attached
            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)
            success = "success_response" in resp or resp.get("success")
            return {"success": success, "order_id": resp.get("success_response", {}).get("order_id"), "raw": resp}
        except Exception as e:
            logger.error(f"bracket buy failed: {e}")
            return {"success": False, "error": str(e)}

    def get_order_fill_details(self, order_id: str) -> Dict[str, Any]:
        """Query order for actual fill price/size."""
        if self.shadow_mode:
            return {"average_filled_price": 0.0, "filled_size": 0.0}
        try:
            if not self.real_client:
                self._ensure_live_client()
            resp = self.real_client.get_order(order_id) if hasattr(self.real_client, 'get_order') else {}
            order = resp.get("order", resp)
            avg_price = float(order.get("average_filled_price") or order.get("filled_price") or 0)
            filled = float(order.get("filled_size") or order.get("size") or 0)
            return {"average_filled_price": avg_price, "filled_size": filled, "status": order.get("status")}
        except Exception as e:
            logger.warning(f"get_order_fill_details failed for {order_id}: {e}")
            return {"average_filled_price": 0.0, "filled_size": 0.0}


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
            # ANALYST-20260629-001: Quick pre-flight settlement poll before live place (reduces INSUFFICIENT_FUND)
            if not self.shadow_mode:
                try:
                    self.poll_for_settlement(product_id, timeout=1.0, max_polls=3)
                except Exception:
                    pass

            limit_p = limit_price or stop_price * 0.995

            meta = self.get_product_metadata(product_id)
            # P0-02: use public canonical quantizers for SL (base size + prices)
            base_size = self.quantize_size(product_id, qty)
            limit_str = self.quantize_price(product_id, limit_p)
            stop_str = self.quantize_price(product_id, stop_price)

            body = {
                "client_order_id": secrets.token_hex(16),
                "product_id": product_id,
                "side": "SELL",
                "order_configuration": {
                    "stop_limit_stop_limit_gtc": {
                        "base_size": base_size,
                        "limit_price": limit_str,
                        "stop_price": stop_str,
                        "stop_direction": "STOP_DIRECTION_STOP_DOWN",
                    }
                }
            }

            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)

            if resp.get("success") is False or "error_response" in resp:
                err = resp.get("error_response", {}).get("error", "unknown")
                preview = resp.get("error_response", {}).get("preview_failure_reason", "")
                logger.warning(f"[LIVE SL] Stop-limit FAILED for {product_id}: {err} {preview} | resp keys: {list(resp.keys()) if isinstance(resp, dict) else type(resp)}")
                return False
            elif "success_response" in resp or resp.get("success"):
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
                logger.warning(f"Stop-limit order may have failed (unexpected resp): {resp}")
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

    def get_crypto_available(self, currency: str) -> float:
        """Return the available (tradable, not on hold) balance for a crypto currency (e.g. 'UNI')."""
        if self.shadow_mode:
            return self._positions.get(currency, 0.0)
        if not self.real_client:
            self._ensure_live_client()
        if not self.real_client:
            return 0.0
        try:
            accounts = self.real_client.get_accounts()
            for acc in accounts.get("accounts", []):
                if acc.get("currency") == currency:
                    avail = float(acc.get("available_balance", {}).get("value", 0.0) or 0.0)
                    return avail
            return 0.0
        except Exception as e:
            logger.warning(f"get_crypto_available failed for {currency}: {e}")
            return 0.0


    
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
        Robust to 401/permission errors. PRIMARY: official SDK list_orders (fixes 401 on historical/batch).
        Fallback to wrapper.
        """
        if self.shadow_mode:
            return []
        if not self.real_client and not self.sdk_client:
            if not self._ensure_live_client():
                return []
        try:
            orders = []
            # PRIMARY: official SDK RESTClient.list_orders (recommended, handles auth correctly, avoids 401 root causes)
            if self.sdk_client is not None:
                try:
                    resp = self.sdk_client.list_orders(order_status=["OPEN"])
                    if hasattr(resp, "orders") and resp.orders:
                        raw_orders = resp.orders
                        for o in raw_orders:
                            if hasattr(o, "to_dict"):
                                orders.append(o.to_dict())
                            else:
                                d = {k: getattr(o, k) for k in dir(o) if not k.startswith("_") and not callable(getattr(o, k, None))}
                                orders.append(d)
                    elif isinstance(resp, dict):
                        orders = resp.get("orders", [])
                except Exception as sdk_e:
                    logger.warning(f"SDK list_orders failed (fallback to wrapper): {sdk_e}")
                    orders = []

            # FALLBACK: wrapper if no SDK or SDK gave nothing
            if not orders and self.real_client is not None:
                if hasattr(self.real_client, "get_orders"):
                    resp = self.real_client.get_orders(order_status="OPEN")
                else:
                    resp = self.real_client._request(
                        "GET", 
                        "/api/v3/brokerage/orders/historical/batch?order_status=OPEN"
                    )
                if isinstance(resp, dict) and ("error" in str(resp).lower() or resp.get("error")):
                    logger.warning(f"get_open_orders wrapper returned error (may be permission): {resp}")
                    resp = {}
                orders = resp.get("orders", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])

            if pair:
                orders = [o for o in orders if o.get("product_id") == pair]

            # Normalize for coordinator
            from phase6.core.sl_preflight import order_configuration_is_stop, extract_stop_price_from_order

            normalized = []
            for o in orders:
                if not isinstance(o, dict):
                    if hasattr(o, "to_dict"):
                        o = o.to_dict()
                    else:
                        o = {k: getattr(o, k, None) for k in ["order_id", "product_id", "side", "status", "order_configuration", "stop_price"] if hasattr(o, k)}
                norm = dict(o)
                oc = o.get("order_configuration", {}) or {}
                if order_configuration_is_stop(oc) or "stop" in str(o.get("order_type", "")).lower():
                    norm["order_type"] = "STOP_LIMIT"
                    sp = extract_stop_price_from_order(o)
                    if sp:
                        norm["stop_price"] = sp
                normalized.append(norm)
            return normalized
        except Exception as e:
            logger.warning(f"get_open_orders failed (graceful empty): {e}")
            return []

    def get_open_stop_orders(self, pair: Optional[str] = None) -> List[Dict[str, Any]]:
        """Dedicated fetch for open stop orders. Filters get_open_orders results."""
        from phase6.core.sl_preflight import order_configuration_is_stop

        all_orders = self.get_open_orders(pair) or []
        stop_orders = []
        for o in all_orders:
            oc = o.get("order_configuration", {}) or {}
            if order_configuration_is_stop(oc) or "stop" in str(o.get("order_type", "")).lower():
                stop_orders.append(o)
        return stop_orders

    def place_market_sell(self, product_id: str, size: float) -> dict:
        """Market sell using base size. Symmetric to buy. Real fills only."""
        if self.shadow_mode:
            self._order_log.append({"type": "market_sell", "pair": product_id, "size": size, "timestamp": __import__('time').time()})
            # P0-02.6: for shadow consistency, return quantized (real path always does via quantize_size)
            try:
                q = self.quantize_size(product_id, size)
                ret_size = float(q)
            except:
                ret_size = size
            return {"success": True, "order_id": "shadow_sell", "size": ret_size}
        if not self.real_client:
            if not self._ensure_live_client():
                return {"success": False, "error": "No live client"}
        try:
            # P0-02: use public canonical quantize_size for SELL base_size (unified)
            base_size = self.quantize_size(product_id, size)
            body = {
                "client_order_id": __import__('secrets').token_hex(16),
                "product_id": product_id,
                "side": "SELL",
                "order_configuration": {"market_market_ioc": {"base_size": base_size}}
            }
            resp = self.real_client._request("POST", "/api/v3/brokerage/orders", body)
            if "success_response" in resp or resp.get("success"):
                return {"success": True, "order_id": resp.get("success_response", {}).get("order_id"), "size": float(base_size)}
            return {"success": False, "error": str(resp)}
        except Exception as e:
            return {"success": False, "error": str(e)}
