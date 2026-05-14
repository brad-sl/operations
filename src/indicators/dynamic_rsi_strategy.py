"""
Dynamic RSI Trading Strategy Module

Implements the Dynamic RSI regime-based trading strategy with:
- Market regime detection (DOWNTREND, SIDEWAYS, UPTREND)
- Dynamic RSI thresholds adjusted per regime
- Position sizing scaled by regime and volatility
- Weighted signal: 60% sentiment + 40% RSI
- ATR-based volatility monitoring

Reference: DYNAMIC_RSI_FOR_TRADERS.md
Author: Brad Slusher
"""

from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np
from datetime import datetime, timedelta


class MarketRegime(Enum):
    """Market regimes based on 24h price change."""
    DOWNTREND = "downtrend"    # 24h change < -2%
    SIDEWAYS = "sideways"       # -2% <= 24h change <= +2%
    UPTREND = "uptrend"         # 24h change > +2%


@dataclass
class RSIThresholds:
    """Dynamic RSI buy/sell thresholds."""
    buy: float
    sell: float
    
    def __repr__(self):
        return f"RSI({self.buy}/{self.sell})"


@dataclass
class SignalContext:
    """Full context for a trading decision."""
    pair: str
    current_price: float
    rsi: float
    sentiment_score: float
    regime: MarketRegime
    thresholds: RSIThresholds
    position_size_multiplier: float
    volatility_pct: float
    final_score: float  # 0.6 * sentiment + 0.4 * (rsi/100)
    signal: str  # BUY, SELL, HOLD
    confidence: float  # 0.0-1.0


class MarketRegimeDetector:
    """Detects market regime from 24h price change."""
    
    DOWNTREND_THRESHOLD = -0.02  # -2%
    UPTREND_THRESHOLD = 0.02      # +2%
    CHECK_INTERVAL_HOURS = 6
    
    def __init__(self):
        self.last_check_time = None
        self.last_regime = MarketRegime.SIDEWAYS
        self.price_24h_ago = None
    
    def detect_regime(self, current_price: float, price_history: List[Tuple[float, datetime]] = None) -> MarketRegime:
        """
        Detect market regime from 24h price change.
        
        Args:
            current_price: Current trading price
            price_history: List of (price, timestamp) tuples for accurate 24h lookback
        
        Returns:
            MarketRegime enum
        """
        now = datetime.utcnow()
        
        # Check every 6 hours (avoid constant recalculation)
        if self.last_check_time and (now - self.last_check_time).total_seconds() < self.CHECK_INTERVAL_HOURS * 3600:
            return self.last_regime
        
        if price_history and len(price_history) > 1:
            # Find price from ~24h ago
            cutoff_time = now - timedelta(hours=24)
            price_24h_ago = None
            
            for price, ts in reversed(price_history):
                if ts <= cutoff_time:
                    price_24h_ago = price
                    break
            
            if price_24h_ago is None and len(price_history) > 0:
                price_24h_ago = price_history[0][0]  # Use oldest available
        else:
            # Use previously stored price or assume no change
            price_24h_ago = self.price_24h_ago or current_price
        
        self.price_24h_ago = price_24h_ago
        
        # Calculate 24h change %
        change_pct = (current_price - price_24h_ago) / price_24h_ago if price_24h_ago > 0 else 0
        
        # Determine regime
        if change_pct < self.DOWNTREND_THRESHOLD:
            regime = MarketRegime.DOWNTREND
        elif change_pct > self.UPTREND_THRESHOLD:
            regime = MarketRegime.UPTREND
        else:
            regime = MarketRegime.SIDEWAYS
        
        self.last_regime = regime
        self.last_check_time = now
        
        return regime
    
    def get_thresholds(self, regime: MarketRegime) -> RSIThresholds:
        """Get dynamic RSI thresholds for a market regime."""
        if regime == MarketRegime.DOWNTREND:
            return RSIThresholds(buy=40, sell=60)
        elif regime == MarketRegime.UPTREND:
            return RSIThresholds(buy=20, sell=80)
        else:  # SIDEWAYS
            return RSIThresholds(buy=30, sell=70)
    
    def get_position_size_multiplier(self, regime: MarketRegime) -> float:
        """Get position size multiplier for a market regime."""
        if regime == MarketRegime.DOWNTREND:
            return 0.75  # 75% position size
        elif regime == MarketRegime.UPTREND:
            return 1.25  # 125% position size
        else:  # SIDEWAYS
            return 1.0   # 100% position size


class ATRCalculator:
    """Calculate Average True Range (ATR) for volatility."""
    
    def __init__(self, period: int = 14):
        self.period = period
    
    def calculate_atr(self, candles: List[Dict]) -> float:
        """
        Calculate ATR from candle data.
        
        Args:
            candles: List of dicts with keys: high, low, close
        
        Returns:
            ATR as percentage of current price
        """
        if len(candles) < self.period:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        if not true_ranges:
            return 0.0
        
        atr = np.mean(true_ranges[-self.period:])
        current_price = candles[-1]['close']
        
        return (atr / current_price) * 100 if current_price > 0 else 0.0
    
    def get_volatility_multiplier(self, atr_pct: float) -> float:
        """
        Get position size multiplier based on volatility (ATR).
        
        High volatility (ATR > 5%): reduce position to 50%
        Moderate volatility (3-5%): reduce to 75%
        Low volatility (< 3%): full 100%
        """
        if atr_pct > 5.0:
            return 0.5
        elif atr_pct > 3.0:
            return 0.75
        else:
            return 1.0


class DynamicRSISignalCalculator:
    """Calculate weighted trading signals using dynamic RSI."""
    
    SENTIMENT_WEIGHT = 0.6
    RSI_WEIGHT = 0.4
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.atr_calculator = ATRCalculator(period=14)
        self.logger = logging.getLogger(__name__)
    
    def calculate_signal(
        self,
        pair: str,
        current_price: float,
        rsi: float,
        sentiment_score: float,
        price_history: Optional[List[Tuple[float, datetime]]] = None,
        candles: Optional[List[Dict]] = None,
    ) -> SignalContext:
        """
        Calculate complete trading signal with dynamic RSI logic.
        
        Args:
            pair: Trading pair (e.g., "BTC-USD")
            current_price: Current market price
            rsi: RSI value (0-100)
            sentiment_score: Sentiment score (-1.0 to +1.0)
            price_history: List of (price, timestamp) for regime detection
            candles: List of candle dicts for ATR calculation
        
        Returns:
            SignalContext with buy/sell/hold decision and confidence
        """
        # Detect market regime
        regime = self.regime_detector.detect_regime(current_price, price_history)
        
        # Get regime-specific thresholds
        thresholds = self.regime_detector.get_thresholds(regime)
        
        # Get position size multiplier for regime
        regime_multiplier = self.regime_detector.get_position_size_multiplier(regime)
        
        # Calculate volatility multiplier
        volatility_multiplier = 1.0
        volatility_pct = 0.0
        if candles:
            volatility_pct = self.atr_calculator.calculate_atr(candles)
            volatility_multiplier = self.atr_calculator.get_volatility_multiplier(volatility_pct)
        
        # Combined position size multiplier
        position_size_multiplier = regime_multiplier * volatility_multiplier
        
        # Normalize sentiment (-1.0..+1.0) to RSI-like scale (0..100)
        sentiment_normalized = (sentiment_score + 1.0) * 50  # -1→0, 0→50, +1→100
        
        # Calculate weighted signal
        final_score = (
            self.SENTIMENT_WEIGHT * sentiment_normalized +
            self.RSI_WEIGHT * rsi
        )
        
        # Generate signal
        signal, confidence = self._generate_signal(rsi, thresholds, sentiment_score, regime)
        
        return SignalContext(
            pair=pair,
            current_price=current_price,
            rsi=rsi,
            sentiment_score=sentiment_score,
            regime=regime,
            thresholds=thresholds,
            position_size_multiplier=position_size_multiplier,
            volatility_pct=volatility_pct,
            final_score=final_score,
            signal=signal,
            confidence=confidence,
        )
    
    def _generate_signal(
        self,
        rsi: float,
        thresholds: RSIThresholds,
        sentiment_score: float,
        regime: MarketRegime,
    ) -> Tuple[str, float]:
        """
        Generate BUY/SELL/HOLD signal.
        
        Rules:
        - BUY if RSI < buy_threshold AND sentiment > -0.3
        - SELL if RSI > sell_threshold OR (RSI > 50 AND sentiment < -0.2)
        - HOLD otherwise
        
        Confidence: Higher when signal aligns with sentiment direction
        """
        signal = "HOLD"
        confidence = 0.5
        
        # Buy signal
        if rsi < thresholds.buy and sentiment_score > -0.3:
            signal = "BUY"
            # Confidence increases if sentiment is strongly bullish
            confidence = min(0.75 + (sentiment_score * 0.25), 1.0)
        
        # Sell signal
        elif rsi > thresholds.sell or (rsi > 50 and sentiment_score < -0.2):
            signal = "SELL"
            # Confidence increases if sentiment is bearish
            confidence = min(0.75 + (abs(sentiment_score) * 0.25), 1.0)
        
        # HOLD has base confidence
        else:
            confidence = 0.5
        
        return signal, confidence


# Convenience function for quick signal calculation
def calculate_dynamic_rsi_signal(
    pair: str,
    current_price: float,
    rsi: float,
    sentiment_score: float,
    price_history: Optional[List[Tuple[float, datetime]]] = None,
    candles: Optional[List[Dict]] = None,
) -> SignalContext:
    """
    Quick wrapper to calculate a dynamic RSI signal.
    
    Usage:
        signal = calculate_dynamic_rsi_signal(
            pair="BTC-USD",
            current_price=67500,
            rsi=45.0,
            sentiment_score=0.3,
            price_history=[(67000, now - 24h), (67500, now)],
        )
        print(f"Signal: {signal.signal}, Position: {signal.position_size_multiplier}x")
    """
    calculator = DynamicRSISignalCalculator()
    return calculator.calculate_signal(pair, current_price, rsi, sentiment_score, price_history, candles)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Simulate a downtrend scenario
    signal = calculate_dynamic_rsi_signal(
        pair="BTC-USD",
        current_price=65000.0,  # Down from 67000
        rsi=35.0,
        sentiment_score=0.1,  # Slightly bullish despite downtrend
        price_history=[
            (67000.0, datetime.utcnow() - timedelta(hours=24)),
            (65000.0, datetime.utcnow()),
        ],
    )
    
    print(f"\n=== Downtrend Example ===")
    print(f"Pair: {signal.pair}")
    print(f"Price: ${signal.current_price:,.2f}")
    print(f"RSI: {signal.rsi:.1f}")
    print(f"Sentiment: {signal.sentiment_score:.2f}")
    print(f"Regime: {signal.regime.value}")
    print(f"Thresholds: {signal.thresholds}")
    print(f"Position Size: {signal.position_size_multiplier:.2f}x (regime: {signal.position_size_multiplier:.2f}x)")
    print(f"Final Score: {signal.final_score:.2f}")
    print(f"Signal: {signal.signal} (confidence: {signal.confidence:.2f})")
