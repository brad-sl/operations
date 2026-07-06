"""
trading/factory.py

Factory for creating TradingClient instances.

Config-driven. The single place new bots should obtain clients.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .client import (
    ShadowTradingClient,
    MockTradingClient,
    CoinbaseLiveClient,
    TradingClient,
)

def create_trading_client(
    mode: str = "shadow",
    exchange: str = "coinbase",
    config: Optional[Dict[str, Any]] = None,
    initial_capital: Optional[float] = None,
    **kwargs,
) -> TradingClient:
    """
    Create appropriate TradingClient based on mode.
    """
    config = config or {}
    if initial_capital is None:
        initial_capital = config.get("max_deployable_usd") or 1000.0

    if exchange != "coinbase":
        raise NotImplementedError(f"Exchange {exchange} not yet supported in platform layer")

    mode = (mode or "shadow").lower()
    if mode == "shadow":
        return ShadowTradingClient(initial_capital=initial_capital, **kwargs)
    if mode == "mock":
        return MockTradingClient(initial_capital=initial_capital, **kwargs)
    if mode == "paper":
        client = ShadowTradingClient(initial_capital=initial_capital, **kwargs)
        client.mode = "paper"
        return client
    if mode == "live":
        return CoinbaseLiveClient(initial_capital=initial_capital, **kwargs)

    # default shadow
    return ShadowTradingClient(initial_capital=initial_capital, **kwargs)
