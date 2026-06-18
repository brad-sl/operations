"""
ATR Calculator (Phase 6 Risk Module)

Provides Average True Range (ATR) calculation using Wilder's smoothing method.
This is a foundational volatility measure used for:
- Dynamic position sizing
- Volatility-adjusted risk
- Regime detection

Public API:
- calculate_atr(highs, lows, closes, period=14) -> float | None
- calculate_atr_series(highs, lows, closes, period=14) -> list[float]
"""

from typing import List, Optional


class ATRCalculator:
    def __init__(self, default_period: int = 14):
        self.default_period = default_period

    def calculate_true_range(self, high: float, low: float, prev_close: float) -> float:
        """Calculate True Range for a single bar."""
        return max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )

    def calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: Optional[int] = None
    ) -> Optional[float]:
        """
        Return the latest ATR value using Wilder's smoothing.

        Returns None if insufficient data.
        """
        period = period or self.default_period
        n = len(highs)

        if n < period + 1:
            return None

        # Calculate initial ATR (simple average of first 'period' True Ranges)
        tr_values = []
        for i in range(1, period + 1):
            tr = self.calculate_true_range(highs[i], lows[i], closes[i - 1])
            tr_values.append(tr)

        atr = sum(tr_values) / period

        # Apply Wilder's smoothing for remaining bars
        for i in range(period + 1, n):
            tr = self.calculate_true_range(highs[i], lows[i], closes[i - 1])
            atr = (atr * (period - 1) + tr) / period

        return round(atr, 8)

    def calculate_atr_series(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: Optional[int] = None
    ) -> List[Optional[float]]:
        """
        Return the full ATR series (same length as input).
        Early values will be None until enough data is available.
        """
        period = period or self.default_period
        n = len(highs)
        result: List[Optional[float]] = [None] * n

        if n < period + 1:
            return result

        # Initial ATR
        tr_values = []
        for i in range(1, period + 1):
            tr = self.calculate_true_range(highs[i], lows[i], closes[i - 1])
            tr_values.append(tr)

        atr = sum(tr_values) / period
        result[period] = round(atr, 8)

        # Continue smoothing
        for i in range(period + 1, n):
            tr = self.calculate_true_range(highs[i], lows[i], closes[i - 1])
            atr = (atr * (period - 1) + tr) / period
            result[i] = round(atr, 8)

        return result


# Convenience function
def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:
    """Quick function interface."""
    calc = ATRCalculator()
    return calc.calculate_atr(highs, lows, closes, period)