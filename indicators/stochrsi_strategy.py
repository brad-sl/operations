#!/usr/bin/env python3
"""
StochRSI Strategy Module — Phase 5
Implements StochRSI(14,3,3) crossover detection for oversold entries.
"""

import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class StochRSISignalCalculator:
    """
    StochRSI-based entry signal detector.
    
    Entry: %K > %D crossover while StochRSI < oversold_threshold (e.g., 0.2)
    Optional: Sentiment filter (60/40 weighting)
    """
    
    def __init__(self, rsi_period: int = 14, k_smooth: int = 3, d_smooth: int = 3, 
                 oversold_threshold: float = 0.2, sentiment_weight: float = 0.6):
        self.rsi_period = rsi_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.oversold_threshold = oversold_threshold
        self.sentiment_weight = sentiment_weight
        self.last_k = None
        self.last_d = None
    
    @staticmethod
    def compute_rsi(prices: list, period: int = 14) -> float:
        """Compute RSI(period)"""
        if len(prices) < period + 1:
            return 50.0
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 0.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
    
    def compute_stochrsi(self, prices: list) -> Tuple[float, float, float]:
        """
        Compute StochRSI %K, %D, and normalized value (0-1).
        
        Returns:
            (k_value, d_value, stochrsi_normalized)
        """
        if len(prices) < self.rsi_period + self.k_smooth:
            return 50.0, 50.0, 0.5
        
        # Compute RSI values over rolling window
        rsi_values = []
        for i in range(len(prices) - self.rsi_period - self.k_smooth + 1, len(prices)):
            window = prices[max(0, i - self.rsi_period):i + 1]
            if len(window) >= self.rsi_period:
                rsi = self.compute_rsi(window, self.rsi_period)
                rsi_values.append(rsi)
        
        if not rsi_values or len(rsi_values) < self.k_smooth:
            return 50.0, 50.0, 0.5
        
        # %K = (RSI - min_RSI) / (max_RSI - min_RSI) * 100
        min_rsi = min(rsi_values[-self.k_smooth:])
        max_rsi = max(rsi_values[-self.k_smooth:])
        
        if max_rsi == min_rsi:
            k_value = 50.0
        else:
            current_rsi = rsi_values[-1]
            k_value = ((current_rsi - min_rsi) / (max_rsi - min_rsi)) * 100.0
        
        # %D = SMA(%K, d_smooth)
        # Approximate: use last d_smooth RSI values
        d_value = np.mean(rsi_values[-self.d_smooth:]) if len(rsi_values) >= self.d_smooth else 50.0
        
        # Normalized StochRSI (0-1)
        stochrsi_norm = k_value / 100.0
        
        return k_value, d_value, stochrsi_norm
    
    def detect_signal(self, prices: list, sentiment: Optional[float] = None) -> Tuple[str, float]:
        """
        Detect entry signal: BUY if %K > %D crossover while StochRSI < oversold.
        
        Returns:
            (signal, confidence)
            signal: 'BUY', 'HOLD', or 'SELL'
            confidence: 0.0-1.0
        """
        if len(prices) < self.rsi_period + self.k_smooth + 1:
            return 'HOLD', 0.0
        
        k, d, stochrsi = self.compute_stochrsi(prices)
        prev_k = self.last_k if self.last_k is not None else d
        
        # Crossover detection: %K crossed above %D
        crossover = (prev_k <= d) and (k > d)
        oversold = stochrsi < self.oversold_threshold
        
        # Update for next cycle
        self.last_k = k
        self.last_d = d
        
        signal = 'HOLD'
        confidence = 0.0
        
        if crossover and oversold:
            signal = 'BUY'
            base_confidence = 0.7  # Crossover + oversold = good signal
            
            if sentiment is not None:
                # Sentiment filter: 60/40 weighting
                sentiment_norm = (sentiment + 1.0) / 2.0  # Convert -1..1 to 0..1
                weighted = (self.sentiment_weight * sentiment_norm + 
                           (1 - self.sentiment_weight) * (stochrsi / self.oversold_threshold))
                confidence = min(1.0, base_confidence * (1.0 + 0.2 * (weighted - 0.5)))
            else:
                confidence = base_confidence
        
        return signal, confidence
    
    def get_signal_context(self) -> dict:
        """Return current signal state for logging"""
        return {
            'k': self.last_k,
            'd': self.last_d,
            'oversold_threshold': self.oversold_threshold
        }


def compute_atr(ohlcv_df, period: int = 14) -> float:
    """
    Compute Average True Range.
    
    Args:
        ohlcv_df: DataFrame with columns 'h', 'l', 'c'
        period: ATR period
    
    Returns:
        ATR value (absolute, not percentage)
    """
    if len(ohlcv_df) < period:
        return (ohlcv_df['h'].iloc[-1] - ohlcv_df['l'].iloc[-1]) if len(ohlcv_df) > 0 else 0.0
    
    # True Range = max(h-l, |h-prev_c|, |l-prev_c|)
    tr = np.maximum(
        ohlcv_df['h'].values - ohlcv_df['l'].values,
        np.maximum(
            np.abs(ohlcv_df['h'].values - np.concatenate([[ohlcv_df['c'].iloc[0]], ohlcv_df['c'].values[:-1]])),
            np.abs(ohlcv_df['l'].values - np.concatenate([[ohlcv_df['c'].iloc[0]], ohlcv_df['c'].values[:-1]]))
        )
    )
    
    # ATR = SMA(TR, period)
    atr = np.mean(tr[-period:])
    return atr


class ATRStopCalculator:
    """Calculate adaptive stop loss based on 2×ATR"""
    
    def __init__(self, atr_multiple: float = 2.0, min_sl_pct: float = -0.02, max_sl_pct: float = -0.05):
        self.atr_multiple = atr_multiple
        self.min_sl_pct = min_sl_pct  # -2% minimum
        self.max_sl_pct = max_sl_pct  # -5% maximum
    
    def calculate_stop_loss(self, entry_price: float, atr: float) -> float:
        """
        Calculate stop loss price based on 2×ATR.
        
        Args:
            entry_price: Entry price
            atr: ATR value (absolute)
        
        Returns:
            Stop loss price (absolute)
        """
        sl_pct = -(self.atr_multiple * atr / entry_price)
        sl_pct = max(self.max_sl_pct, min(self.min_sl_pct, sl_pct))  # Clamp to bounds
        sl_price = entry_price * (1.0 + sl_pct)
        return sl_price
    
    def get_stop_loss_pct(self, entry_price: float, atr: float) -> float:
        """Get stop loss as percentage"""
        sl_pct = -(self.atr_multiple * atr / entry_price)
        sl_pct = max(self.max_sl_pct, min(self.min_sl_pct, sl_pct))
        return sl_pct
