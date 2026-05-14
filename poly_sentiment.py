#!/usr/bin/env python3
"""
Polymarket Sentiment Fetcher for Cryptocurrency Trading
Retrieves market odds as sentiment proxy
"""

import os
import logging
import subprocess
import json
from typing import Dict, Any

class PolymarketSentimentFetcher:
    def __init__(self, weight: float = 0.2):
        """
        Initialize Polymarket sentiment fetcher
        
        :param weight: Sentiment source weight in composite score
        """
        self.weight = weight
        self.logger = logging.getLogger(__name__)
        
        # Caching mechanism
        self.cache_dir = os.path.join(
            os.path.dirname(__file__), 
            'sentiment_cache'
        )
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_file(self, pair: str) -> str:
        """Generate cache filename for Polymarket sentiment"""
        return os.path.join(
            self.cache_dir, 
            f"{pair}_polymarket_sentiment_cache.json"
        )
    
    def _is_cache_valid(self, cache_path: str) -> bool:
        """Check if cached sentiment is recent (1 hour)"""
        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            from datetime import datetime, timedelta
            cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
            return (datetime.now() - cache_time) < timedelta(hours=1)
        except Exception:
            return False
    
    def get_sentiment(self, pair: str) -> float:
        """
        Fetch Polymarket sentiment for cryptocurrency pair
        
        :param pair: Cryptocurrency pair (e.g., 'BTC-USD')
        :return: Sentiment score based on market odds (-1 to 1)
        """
        cache_path = self._get_cache_file(pair)
        
        # Check cache first
        if self._is_cache_valid(cache_path):
            with open(cache_path, 'r') as f:
                return json.load(f)['sentiment']
        
        try:
            # Use last30days CLI to fetch Polymarket odds
            base_currency = pair.split('-')[0]
            query = f"{base_currency} price prediction"
            
            # Execute last30days command
            result = subprocess.run(
                ['last30days', f'{query} Polymarket odds'], 
                capture_output=True, 
                text=True
            )
            
            if result.returncode != 0:
                self.logger.warning(f"Polymarket sentiment fetch failed: {result.stderr}")
                return 0.0
            
            # Parse odds to sentiment score
            # Assumption: Odds > 50% are bullish, convert to -1 to 1 scale
            try:
                odds = float(result.stdout.strip())
                sentiment = (odds - 0.5) * 2  # Convert 0-1 to -1 to 1
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid Polymarket odds: {result.stdout}")
                sentiment = 0.0
            
            # Cache result
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'sentiment': sentiment,
                'pair': pair,
                'raw_odds': result.stdout.strip()
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            self.logger.info(f"Polymarket sentiment for {pair}: {sentiment:.4f}")
            return sentiment
        
        except Exception as e:
            self.logger.error(f"Polymarket sentiment error: {e}")
            return 0.0

def main():
    """Test Polymarket sentiment fetcher"""
    logging.basicConfig(level=logging.INFO)
    fetcher = PolymarketSentimentFetcher()
    
    test_pairs = ['BTC-USD', 'ETH-USD', 'XRP-USD']
    for pair in test_pairs:
        sentiment = fetcher.get_sentiment(pair)
        print(f"{pair} Polymarket Sentiment: {sentiment:.4f}")

if __name__ == '__main__':
    main()