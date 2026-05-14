#!/usr/bin/env python3
"""
indicators/dynamic_rsi_strategy.py

DynamicRSISignalCalculator — extracted from phase3_v4.py logic.
Used by phase4b_smoke_test.py as the signal engine.

Regime detection:
  UPTREND   → buy=20, sell=80
  DOWNTREND → buy=40, sell=60
  SIDEWAYS  → buy=30, sell=70

Signal weighting: 60% sentiment + 40% RSI → weighted_signal
  weighted_signal < buy_thresh  → BUY
  weighted_signal > sell_thresh → SELL
  otherwise                     → HOLD

Position size multiplier:
  UPTREND   → 1.2x (stronger conviction)
  DOWNTREND → 0.7x (smaller position, defensive)
  SIDEWAYS  → 1.0x (base sizing)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class RSIThresholds:
    buy: int
    sell: int

    def __str__(self):
        return f"buy={self.buy}/sell={self.sell}"


@dataclass
class SignalContext:
    """Result of DynamicRSISignalCalculator.calculate_signal()"""
    pair: str
    regime: "Regime"
    thresholds: RSIThresholds
    signal: str                    # 'BUY', 'SELL', or 'HOLD'
    confidence: float              # 0.0 – 1.0
    position_size_multiplier: float
    weighted_signal: float
    rsi: float
    sentiment_score: float
    price: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class Regime:
    """Market regime enum-like class."""
    UPTREND   = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS  = "SIDEWAYS"

    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        return self.value == other.value

    def __repr__(self):
        return f"Regime({self.value})"


REGIME_THRESHOLDS = {
    "UPTREND":   RSIThresholds(buy=20, sell=80),
    "DOWNTREND": RSIThresholds(buy=40, sell=60),
    "SIDEWAYS":  RSIThresholds(buy=30, sell=70),
}

REGIME_SIZE_MULTIPLIER = {
    "UPTREND":   1.2,
    "DOWNTREND": 0.7,
    "SIDEWAYS":  1.0,
}


class MarketRegimeDetector:
    """Detect market regime using 24h price change (same logic as phase3_v4.py)."""

    def __init__(self, threshold_pct: float = 2.0):
        self.threshold_pct = threshold_pct
        self.price_history: List[Tuple[datetime, float]] = []
        self.current_regime = "SIDEWAYS"
        self.last_check: Optional[datetime] = None

    def detect(self, current_price: float, check_interval_hours: int = 6) -> str:
        now = datetime.utcnow()

        # Only re-detect every N hours
        if (self.last_check is not None and
                (now - self.last_check).total_seconds() < check_interval_hours * 3600):
            return self.current_regime

        self.price_history.append((now, current_price))

        # Keep only last 48h
        cutoff = now - timedelta(hours=48)
        self.price_history = [(t, p) for t, p in self.price_history if t > cutoff]

        if len(self.price_history) < 2:
            self.last_check = now
            return self.current_regime

        # Find price ~24h ago (or oldest available)
        price_24h_ago = None
        for t, p in self.price_history:
            if (now - t).total_seconds() >= 24 * 3600:
                price_24h_ago = p
                break
        if price_24h_ago is None:
            price_24h_ago = self.price_history[0][1]

        pct_change = ((current_price - price_24h_ago) / price_24h_ago) * 100

        if pct_change > self.threshold_pct:
            new_regime = "UPTREND"
        elif pct_change < -self.threshold_pct:
            new_regime = "DOWNTREND"
        else:
            new_regime = "SIDEWAYS"

        if new_regime != self.current_regime:
            logger.info(
                f"REGIME CHANGE [{self.current_regime} → {new_regime}] "
                f"24h price change: {pct_change:+.2f}%"
            )
            self.current_regime = new_regime

        self.last_check = now
        return self.current_regime


class DynamicRSISignalCalculator:
    """
    Wire regime detection + RSI + sentiment into a BUY/SELL/HOLD signal.

    Usage:
        calc = DynamicRSISignalCalculator()
        ctx = calc.calculate_signal(
            pair="BTC-USD",
            current_price=67800.0,
            rsi=32.5,
            sentiment_score=0.3,
            price_history=[(price, datetime), ...],
            candles=[{'close': ...}, ...],
        )
        print(ctx.signal, ctx.regime, ctx.thresholds)
    """

    def __init__(self):
        # One regime detector per pair, keyed by pair name
        self._detectors: Dict[str, MarketRegimeDetector] = {}

    def _get_detector(self, pair: str) -> MarketRegimeDetector:
        if pair not in self._detectors:
            self._detectors[pair] = MarketRegimeDetector()
        return self._detectors[pair]

    def calculate_signal(
        self,
        pair: str,
        current_price: float,
        rsi: float,
        sentiment_score: float,
        price_history: List[Tuple[float, datetime]],
        candles: List[Dict],
    ) -> SignalContext:
        """
        Compute BUY/SELL/HOLD with regime-adjusted thresholds.

        Weighting (from phase3_v4): 60% sentiment + 40% RSI
        Sentiment is normalised from [-1, 1] → [0, 100] before weighting.

        Returns SignalContext with full decision context.
        """
        detector = self._get_detector(pair)

        # Build price_history list compatible with detector (list of (datetime, float))
        # price_history from smoke_test is List[Tuple[float, datetime]] — swap order
        detector_history: List[Tuple[datetime, float]] = [
            (ts, px) for (px, ts) in price_history
        ]
        detector.price_history = detector_history  # inject so detect() can use it
        regime_str = detector.detect(current_price)
        regime = Regime(regime_str)

        thresholds = REGIME_THRESHOLDS.get(regime_str, RSIThresholds(buy=30, sell=70))
        size_mult  = REGIME_SIZE_MULTIPLIER.get(regime_str, 1.0)

        # Weighted signal: normalise sentiment [-1,1] → [0,100]
        norm_sentiment = (sentiment_score + 1.0) / 2.0 * 100.0
        weighted = (norm_sentiment * 0.6) + (rsi * 0.4)

        # Signal determination
        if weighted < thresholds.buy:
            signal = "BUY"
            # Confidence scales with how far below threshold
            confidence = min(1.0, (thresholds.buy - weighted) / thresholds.buy)
        elif weighted > thresholds.sell:
            signal = "SELL"
            confidence = min(1.0, (weighted - thresholds.sell) / (100 - thresholds.sell))
        else:
            signal = "HOLD"
            # Confidence is low at midpoint, higher near edges
            mid = (thresholds.buy + thresholds.sell) / 2.0
            confidence = abs(weighted - mid) / (mid - thresholds.buy + 1e-9) * 0.5

        logger.debug(
            f"{pair} | regime={regime_str} | rsi={rsi:.1f} | "
            f"sent={sentiment_score:+.3f} | weighted={weighted:.1f} | "
            f"thresh={thresholds} | signal={signal} | conf={confidence:.2f}"
        )

        return SignalContext(
            pair=pair,
            regime=regime,
            thresholds=thresholds,
            signal=signal,
            confidence=round(confidence, 3),
            position_size_multiplier=size_mult,
            weighted_signal=round(weighted, 2),
            rsi=rsi,
            sentiment_score=sentiment_score,
            price=current_price,
        )
