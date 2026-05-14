#!/usr/bin/env python3
"""
Advanced Cryptocurrency Pair Correlation Calculator
Supports dynamic correlation analysis for trading pair selection
"""

import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Dict, Tuple
import logging
from datetime import datetime, timedelta

class CorrelationCalculator:
    def __init__(self, pairs: List[str], lookback_days: int = 90):
        """
        Initialize correlation calculator
        
        :param pairs: List of cryptocurrency trading pairs
        :param lookback_days: Number of historical days to analyze
        """
        self.pairs = [pair.replace('-USD', '') for pair in pairs]
        self.lookback_days = lookback_days
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _fetch_price_data(self) -> pd.DataFrame:
        """
        Fetch historical price data for specified pairs
        
        :return: DataFrame with daily closing prices
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        
        prices = {}
        for pair in self.pairs:
            try:
                ticker = yf.Ticker(f"{pair}-USD")
                history = ticker.history(start=start_date, end=end_date)
                prices[pair] = history['Close']
            except Exception as e:
                self.logger.warning(f"Could not fetch data for {pair}: {e}")
        
        return pd.DataFrame(prices)
    
    def calculate_correlations(self) -> Dict[Tuple[str, str], float]:
        """
        Calculate pairwise correlations between cryptocurrencies
        
        :return: Dictionary of pair correlations
        """
        prices = self._fetch_price_data()
        correlations = {}
        
        for i, pair1 in enumerate(self.pairs):
            for pair2 in self.pairs[i+1:]:
                corr = prices[pair1].corr(prices[pair2])
                correlations[(pair1, pair2)] = corr
                self.logger.info(f"Correlation {pair1}-{pair2}: {corr:.4f}")
        
        return correlations
    
    def get_low_correlation_pairs(
        self, 
        max_correlation: float = 0.3, 
        top_n: int = 6
    ) -> List[str]:
        """
        Select pairs with low correlation for diversification
        
        :param max_correlation: Maximum allowed correlation
        :param top_n: Number of pairs to return
        :return: List of recommended low-correlation pairs
        """
        correlations = self.calculate_correlations()
        
        # Score pairs based on correlation and market performance
        pair_scores = {}
        for (pair1, pair2), corr in correlations.items():
            if corr < max_correlation:
                pair_scores[pair1] = pair_scores.get(pair1, 0) + 1
                pair_scores[pair2] = pair_scores.get(pair2, 0) + 1
        
        recommended_pairs = sorted(
            pair_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:top_n]
        
        return [f"{pair}-USD" for pair, _ in recommended_pairs]

def main():
    """Example usage and testing"""
    pairs = ['BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'DOGE', 'LINK', 'DOT']
    calculator = CorrelationCalculator(pairs)
    
    print("Low Correlation Pairs:")
    print(calculator.get_low_correlation_pairs())

if __name__ == '__main__':
    main()