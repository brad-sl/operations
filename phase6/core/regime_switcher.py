def get_active_regime(prices: list[float], rsi: float) -> str:
    """Detects market regime based on RSI and momentum proxy."""
    # Simple threshold logic:
    # Bullish: Clear upward momentum or RSI > 60
    # Oversold: RSI < 40 or rapid drop
    # Hybrid: Range-bound
    if rsi < 40:
        return "oversold"
    elif rsi > 60:
        return "bullish"
    else:
        return "hybrid"
