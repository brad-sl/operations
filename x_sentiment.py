#!/usr/bin/env python3
"""
X Sentiment Source for Sentiment Manager
Wraps x_sentiment_fetcher for multi-source sentiment aggregation
"""

from x_sentiment_fetcher import XSentimentFetcher
from typing import Dict, Any

class XApiSentiment:
    """
    Wrapper for X Sentiment Fetcher to integrate with Sentiment Manager
    Provides consistent interface for multi-source sentiment aggregation
    """
    def __init__(self, weight: float = 0.6):
        """
        Initialize X API Sentiment Source
        
        :param weight: Weight of this sentiment source in aggregation
        """
        self.name = "x_api"
        self.weight = weight
        self.fetcher = XSentimentFetcher()
    
    def get_sentiment(self, pair: str) -> float:
        """
        Fetch sentiment for cryptocurrency pair
        
        :param pair: Cryptocurrency pair (e.g., 'BTC-USD')
        :return: Sentiment score (-1 to 1)
        """
        # Fetch sentiment and metadata
        sentiment, metadata = self.fetcher.get_sentiment(pair)
        
        # Log additional details if needed
        print(f"X API Sentiment for {pair}: {sentiment}")
        print(f"  Source Details: {metadata}")
        
        return sentiment

def main():
    """Test X API Sentiment Source"""
    x_sentiment = XApiSentiment()
    
    test_pairs = ['BTC-USD', 'XRP-USD', 'ETH-USD']
    for pair in test_pairs:
        sentiment = x_sentiment.get_sentiment(pair)
        print(f"{pair} Sentiment: {sentiment}")

if __name__ == '__main__':
    main()