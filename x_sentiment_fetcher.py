#!/usr/bin/env python3
"""
X Sentiment Fetcher
Fetches real X sentiment data from Twitter API v2
Implements robust sentiment analysis for cryptocurrency tweets
"""

import os
import json
import requests
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    TextBlob = None

class XSentimentFetcher:
    """
    Sentiment data retrieval and analysis from X API v2.
    
    Provides robust fetching, caching, and basic sentiment scoring
    for cryptocurrency-related tweets.
    """
    BASE_URL = 'https://api.twitter.com/2/tweets/search/recent'
    
    def __init__(self, bearer_token: str):
        """
        Initialize X API sentiment fetcher.
        
        Args:
            bearer_token (str): X API Bearer Token
        
        Raises:
            ValueError: If bearer token is invalid
        """
        if not bearer_token or len(bearer_token.strip()) < 20:
            raise ValueError("Invalid X API Bearer Token")
        
        self.bearer_token = bearer_token.strip()
        self.cache = {}  # Sentiment data cache
        self.cache_duration = 3600  # 1-hour cache window
        
        # Configure detailed logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def _construct_query(self, pair: str) -> str:
        """
        Create a comprehensive query for cryptocurrency sentiment.
        
        Args:
            pair (str): Cryptocurrency pair (e.g., 'BTC-USD')
        
        Returns:
            str: Refined search query
        """
        # Construct a query that captures cryptocurrency discussions
        query_keywords = [
            f'"{pair}"',  # Exact pair mention
            f'{pair.split("-")[0]}',  # Base cryptocurrency symbol
            'crypto', 'blockchain', 'trading', 'investment'
        ]
        
        return ' '.join([
            '(' + ' OR '.join(query_keywords) + ')',
            'lang:en',  # English language
            '-is:retweet',  # Exclude retweets
            '-is:reply'  # Exclude replies to focus on original content
        ])

    def fetch_sentiment(self, pair: str, max_results: int = 100) -> Dict[str, Any]:
        """
        Fetch and analyze sentiment for a cryptocurrency pair.
        
        Args:
            pair (str): Cryptocurrency pair (e.g., 'BTC-USD')
            max_results (int, optional): Maximum number of tweets to fetch. Defaults to 100.
        
        Returns:
            Dict[str, Any]: Sentiment analysis results
        """
        query = self._construct_query(pair)
        
        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
            'User-Agent': 'CryptoBotSentimentAnalyzer/1.1'
        }
        
        params = {
            'query': query,
            'max_results': max_results,
            'tweet.fields': 'created_at,public_metrics,text',
            'expansions': 'author_id'
        }
        
        try:
            response = requests.get(
                self.BASE_URL, 
                headers=headers, 
                params=params, 
                timeout=10
            )
            
            # Detailed error handling
            if response.status_code == 401:
                self.logger.error("Authentication failed: Invalid or expired bearer token")
                raise requests.exceptions.HTTPError("Unauthorized: Check your bearer token")
            elif response.status_code == 429:
                self.logger.warning("Rate limit exceeded: Please wait before making more requests")
                raise requests.exceptions.HTTPError("Rate limit reached")
            
            response.raise_for_status()
            
            data = response.json()
            tweets = data.get('data', [])
            
            # Advanced sentiment scoring
            sentiment_score = self._extract_sentiment(tweets)
            
            # Robust cache management
            cache_entry = {
                'pair': pair,
                'sentiment_score': sentiment_score,
                'tweet_count': len(tweets),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source_tweet_ids': [tweet['id'] for tweet in tweets],
                'tweets': [tweet.get('text', '') for tweet in tweets],
                'cached': False
            }
            
            self.cache[pair] = cache_entry
            return cache_entry
        
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed for {pair}: {e}")
            return {
                'pair': pair,
                'sentiment_score': None, 
                'tweet_count': 0,
                'error': str(e)
            }

    def analyze_sentiment(self, text: str) -> float:
        """
        Calculate sentiment polarity using TextBlob.
        Restored from archived implementation.
        Returns polarity in range [-1.0, 1.0]
        """
        if not TEXTBLOB_AVAILABLE or not text:
            return 0.0
        try:
            return float(TextBlob(text).sentiment.polarity)
        except Exception as e:
            self.logger.warning(f"TextBlob sentiment analysis failed for text: {text[:50]}... Error: {e}")
            return 0.0  # graceful degradation to neutral

    def _extract_sentiment(self, tweets: List[Dict[str, Any]]) -> float:
        """
        Extract sentiment score from tweets using TextBlob polarity + keyword fallback.
        
        Args:
            tweets (List[Dict]): List of tweet dictionaries
        
        Returns:
            float: Sentiment score between -1.0 (very negative) and 1.0 (very positive)
        """
        if not tweets:
            return 0.0
        
        # Keyword-based sentiment scoring (fallback)
        sentiment_keywords = {
            'positive': ['bullish', 'buy', 'moon', 'pump', 'strong', 'gain', 'rise', 'breakthrough'],
            'negative': ['bearish', 'sell', 'crash', 'dump', 'weak', 'loss', 'fall', 'decline']
        }
        
        scores = []
        for tweet in tweets:
            text = tweet.get('text', '')
            text_lower = text.lower()
            
            # TextBlob polarity (primary method - restored)
            polarity = self.analyze_sentiment(text)
            
            # Keyword fallback for robustness
            positive_matches = sum(1 for keyword in sentiment_keywords['positive'] if keyword in text_lower)
            negative_matches = sum(1 for keyword in sentiment_keywords['negative'] if keyword in text_lower)
            keyword_score = 0.0
            if positive_matches + negative_matches > 0:
                keyword_score = (positive_matches - negative_matches) / (positive_matches + negative_matches + 1)
            
            # Hybrid: 70% TextBlob polarity, 30% keyword matching
            if TEXTBLOB_AVAILABLE:
                tweet_score = 0.7 * polarity + 0.3 * keyword_score
            else:
                tweet_score = keyword_score
            
            scores.append(tweet_score)
        
        # Calculate overall sentiment
        return sum(scores) / len(scores) if scores else 0.0

def main():
    """
    Standalone script to test X sentiment fetching.
    """
    # Load bearer token from environment
    TOKEN = os.getenv('X_BEARER_TOKEN')
    if not TOKEN:
        print("❌ Bearer token not set. Check your .env configuration.")
        return
    
    try:
        fetcher = XSentimentFetcher(bearer_token=TOKEN)
        
        # Test multiple cryptocurrency pairs
        test_pairs = ['BTC-USD', 'ETH-USD', 'XRP-USD']
        
        for pair in test_pairs:
            print(f"\n📊 Sentiment Analysis for {pair}")
            print("-" * 40)
            sentiment_data = fetcher.fetch_sentiment(pair)
            
            print(json.dumps(sentiment_data, indent=2))
    
    except Exception as e:
        print(f"❌ Error during sentiment analysis: {e}")

if __name__ == '__main__':
    main()