#!/usr/bin/env python3
"""
X (Twitter) Sentiment Fetcher — Real X API v2 Integration with Failover
Fetches BTC/XRP mentions from X API, calculates sentiment scores
Uses bearer token from .env directly (no xurl CLI dependency)
Cache: 4 hours per pair by default (configurable via sentiment_config.json)
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
    Tries primary X API; on failure, falls back to configured backup sentiment providers
    CRITICAL: Real X API v2 only. NOT synthesized or mocked.
    See: PHASE4B_X_SENTIMENT_SPECIFICATION.md
    """
    
    def __init__(self, cache_dir: str = ".", cache_hours: Optional[int] = None):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "x_sentiment_cache.json"
        self.cache = self._load_cache()
        self._sentiment_config = self._load_sentiment_config()
        # Determine cache hours: config > argument > default 4
        cfg_cache = self._sentiment_config.get("cache", {}) if self._sentiment_config else {}
        configured_hours = int(cfg_cache.get("hours", 4)) if cfg_cache else (cache_hours or 4)
        self.cache_hours = max(1, configured_hours)
        # Get bearer token from .env
        self.bearer_token = os.getenv('X_BEARER_TOKEN')
        if not self.bearer_token:
            logger.warning("X_BEARER_TOKEN not found in .env — X API will be unavailable")
        else:
            logger.info(f"✅ X API bearer token loaded from .env")
        # Calibration/backup log path
        self.calibration_log = self.cache_dir / "sentiment_calibration.jsonl"
        self.calibration_log.parent.mkdir(parents=True, exist_ok=True)
        
    def _load_sentiment_config(self) -> dict:
        config_path = Path(__file__).parent / "config" / "sentiment_config.json"
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load sentiment_config.json: {e}")
            return {}

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
        fetch_time_str = self.cache[pair].get('fetch_time')
        if not fetch_time_str:
            logger.warning(f"Cache entry for {pair} missing 'fetch_time' — treating as stale")
            return False
        try:
            fetch_time = datetime.fromisoformat(fetch_time_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid 'fetch_time' in cache for {pair}: {e} — treating as stale")
            return False
        age = datetime.utcnow() - fetch_time
        is_fresh = age < timedelta(hours=self.cache_hours)
        logger.debug(f"{pair} cache age: {age.total_seconds()/3600:.1f}h (threshold: {self.cache_hours}h), fresh: {is_fresh}")
        return is_fresh

    def _fetch_from_x_api(self, pair: str) -> Tuple[Optional[float], Optional[Dict]]:
        """
        Fetch real sentiment from X API v2 using bearer token
        Returns: (sentiment_score, metadata)
        """
        if not self.bearer_token:
            logger.warning(f"X API bearer token missing, cannot fetch {pair}")
            return None, None

        try:
            # Build query
            if pair == "BTC-USD":
                search_query = "(Bitcoin OR BTC) lang:en -is:retweet"
            else:
                search_query = "(XRP OR Ripple) lang:en -is:retweet"

            logger.info(f"Fetching X sentiment for {pair}: '{search_query}'")
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
                sentiment = 0.0
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

            positive_words = ['bullish', 'pump', 'moon', 'hodl', 'buy', 'long', 'bull', 'gain']
            negative_words = ['bearish', 'dump', 'crash', 'sell', 'short', 'bear', 'loss', 'risk']
            positive_count = 0
            negative_count = 0
            for tweet in tweets:
                text = tweet.get('text', '').lower()
                pos_matches = sum(1 for w in positive_words if w in text)
                neg_matches = sum(1 for w in negative_words if w in text)
                if pos_matches > neg_matches:
                    positive_count += 1
                elif neg_matches > pos_matches:
                    negative_count += 1

            total = positive_count + negative_count if (positive_count + negative_count) > 0 else len(tweets)
            positive_ratio = positive_count / total if total > 0 else 0.5
            sentiment = (positive_ratio * 2) - 1

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

    def _fetch_from_backup(self, pair: str) -> Tuple[Optional[float], Optional[Dict]]:
        """
        Failover to backup sentiment providers if X is unavailable.
        This is a scaffold; fill in real endpoints/keys.
        Returns: (sentiment, metadata) or (None, None)
        """
        # 1) LunarCrush (example scaffold)
        lunar_key = os.getenv("LUNARCRUSH_KEY", "")
        if lunar_key:
            try:
                # Placeholder endpoint — replace with real LunarCrush API call
                symbol = pair.split("-")[0]
                url = f"https://api.lunarcrush.com/v2?data=market&symbol={symbol}&key={lunar_key}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    back_sent = float(data.get("data", {}).get("sentiment", 0.0))
                    metadata = {"source": "LunarCrush", "fetch_time": datetime.utcnow().isoformat(), "pair": pair}
                    return back_sent, metadata
            except Exception as e:
                logger.exception(f"LunarCrush backup failed for {pair}: {e}")

        # 2) CryptoPanic (example scaffold)
        cp_key = os.getenv("CRYPTO_PANIC_KEY", "")
        if cp_key:
            try:
                url = f"https://cryptopanic.com/api/v1/posts/?key={cp_key}&currency={pair}"
                r = requests.get(url, timeout=6)
                if r.status_code == 200:
                    data = r.json()
                    back_sent = float(data.get("data", [{}])[0].get("sentiment", 0.0))
                    metadata = {"source": "CryptoPanic", "fetch_time": datetime.utcnow().isoformat(), "pair": pair}
                    return back_sent, metadata
            except Exception as e:
                logger.exception(f"CryptoPanic backup failed for {pair}: {e}")

        return None, None

    def get_sentiment(self, pair: str, force_refresh: bool = False) -> Tuple[float, Dict]:
        """
        Get sentiment for pair (cached or fresh from X API)
        Returns: (sentiment_score, metadata)
        """
        if not force_refresh and self._is_cache_fresh(pair):
            cached = self.cache[pair]
            age = (datetime.utcnow() - datetime.fromisoformat(cached['fetch_time'])).total_seconds() / 60
            cached['age_minutes'] = int(age)
            logger.info(f"Using cached {pair} sentiment: {cached['sentiment']:.2f} ({int(age)}m old)")
            return cached.get('sentiment', 0.0), cached

        sentiment, metadata = self._fetch_from_x_api(pair)
        if sentiment is None:
            # Fallback to cache if available
            if pair in self.cache:
                logger.warning(f"X API failed, using stale cache for {pair}")
                cached = self.cache[pair]
                try:
                    ft = cached.get('fetch_time')
                    age_min = int((datetime.utcnow() - datetime.fromisoformat(ft)).total_seconds() / 60) if ft else 0
                except (ValueError, TypeError):
                    age_min = 0
                cached['age_minutes'] = age_min
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

        # Cache success
        metadata['sentiment'] = sentiment
        self.cache[pair] = metadata
        self._save_cache()
        return sentiment, metadata

    def log_calibration(self, pair: str, x_sentiment: float, backup_sentiment: float, backup_source: str):
        payload = {
            'timestamp': datetime.utcnow().isoformat(),
            'pair': pair,
            'x_sentiment': x_sentiment,
            'backup_sentiment': backup_sentiment,
            'backup_source': backup_source
        }
        try:
            with open(self.calibration_log, 'a') as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass


if __name__ == '__main__':
    fetcher = XSentimentFetcher()
    print("\n=== Testing X Sentiment Fetcher ===\n")
    for pair in ['BTC-USD', 'XRP-USD']:
        sentiment, metadata = fetcher.get_sentiment(pair, force_refresh=True)
        print(f"{pair}: {sentiment:.2f}")
        print(f"  Source: {metadata.get('source')}")
        print(f"  Tweets: {metadata.get('total_tweets', 'N/A')}")
        print()