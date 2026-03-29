#!/usr/bin/env python3
"""
X (Twitter) Sentiment Fetcher — Real X API v2 Integration
Fetches BTC/XRP mentions from X API, calculates sentiment scores
Uses bearer token from .env directly (no xurl CLI dependency)
Cache: 1 hour per pair by default (configurable via cache_hours param)
CRITICAL SPEC: See PHASE4B_X_SENTIMENT_SPECIFICATION.md
"""

import json
import requests
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env from crypto-bot directory
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)


class XSentimentFetcher:
    """Fetch and cache X (Twitter) sentiment for crypto pairs
    
    CRITICAL: Real X API v2 only. NOT synthesized or mocked.
    See: PHASE4B_X_SENTIMENT_SPECIFICATION.md
    """
    
    def __init__(self, cache_dir: str = ".", cache_hours: int = 1):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "x_sentiment_cache.json"
        self.cache_hours = max(1, int(cache_hours))  # Enforce minimum 1 hour
        self.cache = self._load_cache()
        
        # Get bearer token from .env
        self.bearer_token = os.getenv('X_BEARER_TOKEN')
        if not self.bearer_token:
            logger.warning("X_BEARER_TOKEN not found in .env — X API will be unavailable")
        else:
            logger.info(f"✅ X API bearer token loaded from .env")
        
    def _load_cache(self) -> Dict:
        """Load sentiment cache from disk"""
        if self.cache_file.exists():
            with open(self.cache_file) as f:
                return json.load(f)
        return {}
    
    def _save_cache(self):
        """Save sentiment cache to disk"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _is_cache_fresh(self, pair: str) -> bool:
        """Check if cached sentiment is < cache_hours old"""
        if pair not in self.cache:
            return False
        fetch_time = datetime.fromisoformat(self.cache[pair]['fetch_time'])
        age = datetime.utcnow() - fetch_time
        is_fresh = age < timedelta(hours=self.cache_hours)
        logger.debug(f"{pair} cache age: {age.total_seconds()/3600:.1f}h (threshold: {self.cache_hours}h), fresh: {is_fresh}")
        return is_fresh
    
    def _fetch_from_x_api(self, pair: str) -> Tuple[Optional[float], Optional[Dict]]:
        """
        Fetch real sentiment from X API v2 using bearer token
        Returns: (sentiment_score: -1.0 to +1.0, metadata: dict)
        """
        if not self.bearer_token:
            logger.warning(f"X API bearer token missing, cannot fetch {pair}")
            return None, None
        
        try:
            # Query keywords per pair
            if pair == "BTC-USD":
                search_query = "(Bitcoin OR BTC) lang:en -is:retweet"
            else:  # XRP-USD
                search_query = "(XRP OR Ripple) lang:en -is:retweet"
            
            logger.info(f"Fetching X sentiment for {pair}: '{search_query}'")
            
            # X API v2 endpoint
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": "CryptoTradingBot/1.0"
            }
            params = {
                "query": search_query,
                "max_results": 100,
                "tweet.fields": "created_at,public_metrics,lang",
                "expansions": "author_id"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 401:
                logger.error("❌ X API 401 Unauthorized — bearer token invalid or expired")
                return None, None
            elif response.status_code == 429:
                logger.warning("⏱️ X API rate limited — retrying with cache")
                return None, None
            elif response.status_code != 200:
                logger.error(f"X API error {response.status_code}: {response.text}")
                return None, None
            
            data = response.json()
            tweets = data.get('data', [])
            
            if not tweets:
                logger.warning(f"No tweets found for {pair}")
                sentiment = 0.0  # Neutral if no data
                metadata = {
                    'sentiment': sentiment,
                    'positive_tweets': 0,
                    'negative_tweets': 0,
                    'total_tweets': 0,
                    'source': 'X API v2',
                    'fetch_time': datetime.utcnow().isoformat(),
                    'age_minutes': 0,
                    'note': f'No tweets found for: {search_query}'
                }
                return sentiment, metadata
            
            # Simple sentiment: count tweets with positive/negative language
            # (Production would use NLP model or X's native sentiment)
            positive_words = ['bullish', 'pump', 'moon', 'hodl', 'buy', 'long', 'bull', 'gain']
            negative_words = ['bearish', 'dump', 'crash', 'sell', 'short', 'bear', 'loss', 'risk']
            
            positive_count = 0
            negative_count = 0
            
            for tweet in tweets:
                text = tweet.get('text', '').lower()
                pos_matches = sum(1 for word in positive_words if word in text)
                neg_matches = sum(1 for word in negative_words if word in text)
                
                if pos_matches > neg_matches:
                    positive_count += 1
                elif neg_matches > pos_matches:
                    negative_count += 1
            
            total = positive_count + negative_count if positive_count + negative_count > 0 else len(tweets)
            positive_ratio = positive_count / total if total > 0 else 0.5
            sentiment = (positive_ratio * 2) - 1  # Range: -1.0 to +1.0
            
            metadata = {
                'sentiment': round(sentiment, 3),
                'positive_tweets': positive_count,
                'negative_tweets': negative_count,
                'total_tweets': len(tweets),
                'positive_ratio': round(positive_ratio, 3),
                'source': 'X API v2',
                'fetch_time': datetime.utcnow().isoformat(),
                'age_minutes': 0,
                'query': search_query
            }
            
            logger.info(f"✅ {pair}: {positive_count}+ / {negative_count}- tweets = {sentiment:.2f} sentiment")
            return sentiment, metadata
        
        except requests.exceptions.Timeout:
            logger.error(f"X API timeout for {pair}")
            return None, None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"X API connection error: {e}")
            return None, None
        except Exception as e:
            logger.error(f"X API error: {e}")
            return None, None
    
    def get_sentiment(self, pair: str, force_refresh: bool = False) -> Tuple[float, Dict]:
        """
        Get sentiment for pair (cached or fresh from X API)
        Returns: (sentiment_score: -1.0 to +1.0, metadata: dict with source)
        """
        # Check cache first
        if not force_refresh and self._is_cache_fresh(pair):
            cached = self.cache[pair]
            age = (datetime.utcnow() - datetime.fromisoformat(cached['fetch_time'])).total_seconds() / 60
            cached['age_minutes'] = int(age)
            logger.info(f"Using cached {pair} sentiment: {cached['sentiment']:.2f} ({int(age)}m old)")
            return cached.get('sentiment', 0.0), cached
        
        # Fetch from X API
        sentiment, metadata = self._fetch_from_x_api(pair)
        
        # Handle API failure — fall back to cache
        if sentiment is None:
            if pair in self.cache:
                logger.warning(f"X API failed, using stale cache for {pair}")
                cached = self.cache[pair]
                cached['age_minutes'] = int((datetime.utcnow() - datetime.fromisoformat(cached['fetch_time'])).total_seconds() / 60)
                cached['note'] = 'STALE CACHE (X API failed)'
                return cached.get('sentiment', 0.0), cached
            else:
                logger.warning(f"X API failed and no cache for {pair}, returning neutral")
                return 0.0, {
                    'sentiment': 0.0,
                    'source': 'X API (failed, no cache)',
                    'fetch_time': datetime.utcnow().isoformat(),
                    'note': 'X API unavailable and no cached data'
                }
        
        # Cache successful fetch
        metadata['sentiment'] = sentiment
        self.cache[pair] = metadata
        self._save_cache()
        
        return sentiment, metadata


if __name__ == '__main__':
    # Quick test
    fetcher = XSentimentFetcher()
    
    print("\n=== Testing X Sentiment Fetcher ===\n")
    
    for pair in ['BTC-USD', 'XRP-USD']:
        sentiment, metadata = fetcher.get_sentiment(pair, force_refresh=True)
        print(f"{pair}: {sentiment:.2f}")
        print(f"  Source: {metadata.get('source')}")
        print(f"  Tweets: {metadata.get('total_tweets', 'N/A')}")
        print()
