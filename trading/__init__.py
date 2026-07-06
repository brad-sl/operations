"""
trading package - platform execution layer for ARCH-4.

Exports factory and executor.
"""

from .factory import create_trading_client
from .executor import TradeExecutor
from .client import (
    TradingClient,
    ShadowTradingClient,
    MockTradingClient,
    CoinbaseLiveClient,
)

__all__ = [
    "create_trading_client",
    "TradeExecutor",
    "TradingClient",
    "ShadowTradingClient",
    "MockTradingClient",
    "CoinbaseLiveClient",
]
