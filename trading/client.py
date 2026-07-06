"""
trading/client.py - TradingClient abstractions for platform layer (ARCH-4).

Shadow for safe testing, Live for coinbase.
Follows the interface expected by TradeExecutor.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

try:
    from phase6.core.exchange_client import CoinbaseExchangeClient
except Exception:
    CoinbaseExchangeClient = None

try:
    from .types import TradeResult, AttrDict
except Exception:
    # fallback
    class TradeResult:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.success = kwargs.get('success', False)
    class AttrDict(dict):
        pass

class TradingClient:
    """Base interface."""
    def __init__(self, mode: str = "shadow", initial_capital: Optional[float] = None, **kwargs):
        self.mode = mode.lower()
        self.shadow_mode = self.mode == "shadow"
        self.initial_capital = initial_capital or 1000.0

    def get_account_balance(self, currency: str = "USD") -> float:
        raise NotImplementedError

    def get_positions(self) -> Dict[str, float]:
        raise NotImplementedError

    def get_price(self, pair: str) -> float:
        raise NotImplementedError

    def place_market_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        raise NotImplementedError

    def place_market_sell(self, pair: str, size: float) -> Dict[str, Any]:
        raise NotImplementedError

    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        return {"price_increment": 0.01, "base_increment": 0.001}

    def quantize_size(self, pair: str, size: float) -> float:
        try:
            meta = self.get_product_metadata(pair)
            inc = Decimal(str(meta.get("base_increment", 0.001)))
            dsize = Decimal(str(size)).quantize(inc, rounding=ROUND_DOWN)
            return float(dsize)
        except Exception:
            return round(size, 8)

class ShadowTradingClient(TradingClient):
    """Shadow simulation client for testing and shadow runs. No real trades."""

    def __init__(self, initial_capital: Optional[float] = None, **kwargs):
        super().__init__(mode="shadow", initial_capital=initial_capital, **kwargs)
        self._balance = {"USD": float(initial_capital or 1000.0)}
        self._positions: Dict[str, float] = {}
        self._prices: Dict[str, float] = {}  # can be populated externally
        self._order_log: List[Dict] = []

    def get_account_balance(self, currency: str = "USD") -> float:
        return float(self._balance.get(currency.upper(), 0.0))

    def get_positions(self) -> Dict[str, float]:
        return dict(self._positions)

    def get_price(self, pair: str) -> float:
        p = pair.upper()
        if p in self._prices:
            return self._prices[p]
        # fallback reasonable prices for tests
        fallbacks = {
            "BTC-USD": 65000.0, "ETH-USD": 3400.0, "SOL-USD": 140.0,
            "XRP-USD": 0.52, "DOGE-USD": 0.12, "ADA-USD": 0.36,
            "AVAX-USD": 27.0, "LINK-USD": 13.5, "UNI-USD": 7.8,
            "ARB-USD": 0.72, "OP-USD": 1.65
        }
        return fallbacks.get(p, 100.0)

    def place_market_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        price = self.get_price(pair)
        size = usd_amount / price if price > 0 else 0.0
        size = self.quantize_size(pair, size)
        self._balance["USD"] = self._balance.get("USD", 0) - usd_amount
        self._positions[pair] = self._positions.get(pair, 0.0) + size
        res = {
            "success": True,
            "order_id": f"shadow-buy-{int(time.time()*1000)}",
            "entry_price": round(price, 4),
            "size": size,
            "qty": size,
            "price": price,
            "actual_fill_used": False,
        }
        self._order_log.append({"action": "BUY", "pair": pair, "usd": usd_amount, "res": res})
        return res

    def place_market_sell(self, pair: str, size: float) -> Dict[str, Any]:
        price = self.get_price(pair)
        usd = size * price
        self._positions[pair] = max(0.0, self._positions.get(pair, 0.0) - size)
        self._balance["USD"] = self._balance.get("USD", 0) + usd
        res = {
            "success": True,
            "order_id": f"shadow-sell-{int(time.time()*1000)}",
            "entry_price": round(price, 4),
            "size": size,
            "qty": size,
            "price": price,
        }
        self._order_log.append({"action": "SELL", "pair": pair, "size": size, "res": res})
        return res

    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        # Use dynamic if possible, else defaults
        pid = product_id.upper()
        defaults = {
            "BTC-USD": {"price_increment": 0.01, "base_increment": 0.00000001},
            "ETH-USD": {"price_increment": 0.01, "base_increment": 0.0001},
            "SOL-USD": {"price_increment": 0.01, "base_increment": 0.001},
        }
        return defaults.get(pid, {"price_increment": 0.01, "base_increment": 0.001})

class MockTradingClient(ShadowTradingClient):
    """Alias for mock in factory."""
    pass

class CoinbaseLiveClient(TradingClient):
    """Live client delegating to CoinbaseExchangeClient when available."""

    def __init__(self, initial_capital: Optional[float] = None, **kwargs):
        super().__init__(mode="live", initial_capital=initial_capital, **kwargs)
        self._live_exchange = None
        if CoinbaseExchangeClient is not None:
            try:
                self._live_exchange = CoinbaseExchangeClient(mode="live", initial_capital=initial_capital)
            except Exception as e:
                logger.warning(f"[PLATFORM] Could not init live exchange: {e}")

    def get_account_balance(self, currency: str = "USD") -> float:
        if self._live_exchange and hasattr(self._live_exchange, "get_account_balance"):
            return float(self._live_exchange.get_account_balance(currency))
        return 0.0

    def get_positions(self) -> Dict[str, float]:
        if self._live_exchange and hasattr(self._live_exchange, "get_positions"):
            return self._live_exchange.get_positions() or {}
        return {}

    def get_price(self, pair: str) -> float:
        if self._live_exchange and hasattr(self._live_exchange, "get_price"):
            return float(self._live_exchange.get_price(pair) or 0.0)
        return 0.0

    def place_market_buy(self, pair: str, usd_amount: float) -> Dict[str, Any]:
        if self._live_exchange and hasattr(self._live_exchange, "place_market_buy"):
            return self._live_exchange.place_market_buy(pair, usd_amount) or {"success": False}
        return {"success": False, "error": "no live client"}

    def place_market_sell(self, pair: str, size: float) -> Dict[str, Any]:
        if self._live_exchange and hasattr(self._live_exchange, "place_market_sell"):
            return self._live_exchange.place_market_sell(pair, size) or {"success": False}
        return {"success": False, "error": "no live client"}

    def get_product_metadata(self, product_id: str) -> Dict[str, float]:
        if self._live_exchange and hasattr(self._live_exchange, "get_product_metadata"):
            return self._live_exchange.get_product_metadata(product_id)
        return super().get_product_metadata(product_id)

def get_trading_client(mode: str = "shadow", **kwargs):
    """Convenience."""
    if mode == "shadow":
        return ShadowTradingClient(**kwargs)
    if mode == "live":
        return CoinbaseLiveClient(**kwargs)
    return ShadowTradingClient(**kwargs)
