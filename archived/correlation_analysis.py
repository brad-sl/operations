#!/usr/bin/env python3
"""
Advanced Cryptocurrency Pair Correlation Calculator
Supports dynamic correlation analysis for trading pair selection
"""

import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

class CorrelationCalculator:
    def __init__(self, pairs, lookback_days=90):
        self.pairs = [pair.replace('-USD', '') for pair in pairs]
        self.lookback_days = lookback_days
        self.output_path = os.path.join(
            os.path.dirname(__file__), 
            'config', 
            'pair_correlations.json'
        )
    
    def fetch_price_data(self):
        """Fetch historical price data for specified pairs"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        
        prices = {}
        for pair in self.pairs:
            try:
                ticker = yf.Ticker(f"{pair}-USD")
                history = ticker.history(start=start_date, end=end_date)
                prices[pair] = history['Close']
            except Exception as e:
                print(f"Could not fetch data for {pair}: {e}")
        
        return pd.DataFrame(prices)
    
    def calculate_correlations(self):
        """Calculate pairwise correlations between cryptocurrencies"""
        prices = self.fetch_price_data()
        correlations = {}
        
        for i, pair1 in enumerate(self.pairs):
            for pair2 in self.pairs[i+1:]:
                try:
                    corr = prices[pair1].corr(prices[pair2])
                    correlations[f"{pair1}-{pair2}"] = float(corr)
                except Exception as e:
                    print(f"Correlation error for {pair1}-{pair2}: {e}")
        
        return correlations
    
    def get_low_correlation_pairs(self, max_correlation=0.3, top_n=6):
        """Select pairs with low correlation for diversification"""
        correlations = self.calculate_correlations()
        
        # Score pairs based on correlation
        pair_scores = {}
        for pair_combo, corr in correlations.items():
            if corr < max_correlation:
                p1, p2 = pair_combo.split('-')
                pair_scores[p1] = pair_scores.get(p1, 0) + 1
                pair_scores[p2] = pair_scores.get(p2, 0) + 1
        
        recommended_pairs = sorted(
            pair_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:top_n]
        
        # Save results
        result = {
            "timestamp": datetime.now().isoformat(),
            "correlations": correlations,
            "recommended_pairs": [f"{pair}-USD" for pair, _ in recommended_pairs]
        }
        
        with open(self.output_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"Correlation analysis complete. Results saved to {self.output_path}")
        return result

def main():
    """Run correlation analysis"""
    pairs = ['BTC', 'ETH', 'XRP', 'ADA', 'SOL', 'DOGE', 'LINK', 'DOT']
    calculator = CorrelationCalculator(pairs)
    calculator.get_low_correlation_pairs()

if __name__ == '__main__':
    main()