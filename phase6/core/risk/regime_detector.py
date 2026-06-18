"""
RegimeDetector (Phase 6 Risk Module)

Lightweight market regime detection.
Detects volatility, trend, and correlation regimes to enable
adaptive RSI thresholds and position sizing.

Public API:
- detect(prices, atr, correlation=None) -> dict
"""

from typing import List, Optional, Dict, Any
import statistics


class RegimeDetector:
    def __init__(self):
        self.regimes = ["HIGH_VOL", "LOW_VOL", "TRENDING", "RANGING", "HIGH_CORR"]

    def detect(
        self,
        prices: List[float],
        atr: Optional[float] = None,
        correlation: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Detect current market regime and suggest adjustments.
        """
        result = {
            "regime": "NORMAL",
            "confidence": 0.5,
            "adjustments": {
                "rsi_buy": 30,
                "rsi_sell": 70,
                "position_size_mult": 1.0
            }
        }

        if not prices or len(prices) < 10:
            return result

        # Volatility regime
        if atr:
            avg_price = statistics.mean(prices[-10:])
            atr_pct = (atr / avg_price) * 100 if avg_price > 0 else 0

            if atr_pct > 4.0:
                result["regime"] = "HIGH_VOL"
                result["confidence"] = 0.8
                result["adjustments"]["rsi_buy"] = 28
                result["adjustments"]["rsi_sell"] = 72
                result["adjustments"]["position_size_mult"] = 0.7
            elif atr_pct < 1.5:
                result["regime"] = "LOW_VOL"
                result["confidence"] = 0.7
                result["adjustments"]["position_size_mult"] = 1.2

        # Correlation regime (if provided)
        if correlation and correlation > 0.75:
            if result["regime"] == "NORMAL":
                result["regime"] = "HIGH_CORR"
            result["adjustments"]["position_size_mult"] *= 0.8
            result["confidence"] = max(result["confidence"], 0.75)

        # Simple trend detection
        if len(prices) >= 20:
            short_ma = statistics.mean(prices[-5:])
            long_ma = statistics.mean(prices[-20:])
            if short_ma > long_ma * 1.03:
                result["regime"] = "TRENDING"
            elif short_ma < long_ma * 0.97:
                result["regime"] = "TRENDING"

        return result


def detect_regime(prices: List[float], atr: float = None, correlation: float = None) -> dict:
    """Convenience function."""
    detector = RegimeDetector()
    return detector.detect(prices, atr, correlation)