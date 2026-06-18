"""
SignalGenerator (Phase 6 Core Module)

Centralized signal generation logic supporting multiple modes.
Consumes RSI, ATR, and Sentiment to produce BUY/SELL/HOLD signals.

Modes:
- weighted     : Balanced combination (default)
- conservative : Strict AND conditions (RSI extreme + sentiment alignment)
- rsi_primary  : RSI dominant, others as filters

Public API:
- generate_signal(pair, rsi, atr, sentiment, mode="weighted") -> Signal
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Signal:
    pair: str
    signal: str          # "BUY", "SELL", or "HOLD"
    confidence: float    # 0.0 – 1.0
    reason: str
    timestamp: str = ""


class SignalGenerator:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def generate_signal(
        self,
        pair: str,
        rsi: float,
        atr: Optional[float] = None,
        sentiment: float = 0.0,
        mode: str = "weighted"
    ) -> Signal:
        """
        Generate a single trading signal.
        """
        if mode == "conservative":
            return self._conservative_signal(pair, rsi, sentiment)
        elif mode == "rsi_primary":
            return self._rsi_primary_signal(pair, rsi, atr, sentiment)
        else:
            return self._weighted_signal(pair, rsi, atr, sentiment)

    # ------------------------------------------------------------------
    # Mode Implementations
    # ------------------------------------------------------------------

    def _weighted_signal(self, pair, rsi, atr, sentiment) -> Signal:
        """Balanced weighted approach."""
        score = 0.0
        reasons = []

        # RSI component (primary)
        if rsi < 30:
            score += 0.4
            reasons.append("RSI oversold")
        elif rsi > 70:
            score -= 0.4
            reasons.append("RSI overbought")

        # Sentiment component
        if sentiment > 0.2:
            score += 0.3
            reasons.append("Positive sentiment")
        elif sentiment < -0.2:
            score -= 0.3
            reasons.append("Negative sentiment")

        # ATR component (volatility filter)
        if atr and atr > 0:
            # Higher ATR slightly reduces confidence in extreme signals
            if rsi < 30 or rsi > 70:
                score *= 0.9

        if score > 0.25:
            return Signal(pair, "BUY", min(score, 1.0), " | ".join(reasons) or "Weighted bullish")
        elif score < -0.25:
            return Signal(pair, "SELL", min(abs(score), 1.0), " | ".join(reasons) or "Weighted bearish")
        else:
            return Signal(pair, "HOLD", 0.5, "No strong signal")

    def _conservative_signal(self, pair, rsi, sentiment) -> Signal:
        """Strict AND conditions (legacy Phase 5 style)."""
        if rsi < 30 and sentiment > 0.3:
            return Signal(pair, "BUY", 0.9, "RSI < 30 AND sentiment > 0.3")
        elif rsi > 70 and sentiment < -0.3:
            return Signal(pair, "SELL", 0.9, "RSI > 70 AND sentiment < -0.3")
        else:
            return Signal(pair, "HOLD", 0.4, "Conservative filter not met")

    def _rsi_primary_signal(self, pair, rsi, atr, sentiment) -> Signal:
        """RSI dominant with ATR and sentiment as filters."""
        if rsi < 30:
            conf = 0.7
            if sentiment > 0:
                conf += 0.15
            if atr and atr > 2.0:  # high volatility
                conf -= 0.1
            return Signal(pair, "BUY", min(conf, 1.0), "RSI primary + filters")
        elif rsi > 70:
            conf = 0.7
            if sentiment < 0:
                conf += 0.15
            return Signal(pair, "SELL", min(conf, 1.0), "RSI primary + filters")
        else:
            return Signal(pair, "HOLD", 0.5, "RSI neutral")


# Convenience function
def generate_signal(pair: str, rsi: float, atr: float = None, sentiment: float = 0.0, mode: str = "weighted") -> Signal:
    gen = SignalGenerator()
    return gen.generate_signal(pair, rsi, atr, sentiment, mode)