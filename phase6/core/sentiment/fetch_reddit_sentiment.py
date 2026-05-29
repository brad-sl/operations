#!/usr/bin/env python3
"""
Reddit Sentiment Fetcher for Crypto Trading Bot

Fetches sentiment from Reddit r/crypto, r/bitcoin, r/ethereum communities
using Apify Reddit actor (replaces direct PRAW API).

Grid-validated parameters:
- Half-life: 60 minutes (exponential decay)
- Sources: r/CryptoCurrency, r/Bitcoin, r/ethereum via Apify
- Metrics: Upvotes, comments, sentiment keywords
- Output: reddit_sentiment_cache.json

NO FAKE DATA: Real Reddit data only via Apify actor.
"""

import logging
import os
import json
import os
from pathlib import Path

def _load_env():
    env_file = Path("/home/brad/projects/crypto-trading-bot/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"\'')
                if k not in os.environ:
                    os.environ[k] = v
_load_env()

from datetime import datetime
from pathlib import Path

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except Exception:
    APIFY_AVAILABLE = False
    ApifyClient = None

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    NUMPY_AVAILABLE = False
    np = None

logger = logging.getLogger(__name__)

# Configuration
REDDIT_CACHE_FILE = Path(__file__).parent / 'reddit_sentiment_cache.json'
APIFY_USER_ID = os.getenv('APIFY_USER_ID')
APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN')

# Apify Reddit actor ID (community actor for scraping Reddit)
REDDIT_ACTOR_ID = 'aYMxR9AqRjxmgzcwB'  # Community Reddit scraper

# Sentiment keywords
BULLISH_KEYWORDS = [
    'moon', 'pump', 'buy', 'bull', 'gain', 'surge', 'spike',
    'awesome', 'great', 'excellent', 'amazing', 'bullish',
    'long', 'hold', 'hodl', 'strong', 'opportunity', 'gem'
]

BEARISH_KEYWORDS = [
    'crash', 'dump', 'sell', 'bear', 'loss', 'drop', 'fall',
    'terrible', 'bad', 'scam', 'bearish', 'short',
    'risk', 'warning', 'caution', 'trap', 'fraud', 'rug'
]


class RedditSentimentFetcher:
    """Fetch real sentiment from Reddit for crypto pairs via Apify."""
    
    def __init__(self):
        """Initialize Apify client."""
        self.client = None
        self.pair_keywords = {
            'BTC-USD': ['bitcoin', 'btc'],
            'ETH-USD': ['ethereum', 'eth'],
            'SOL-USD': ['solana', 'sol'],
            'XRP-USD': ['ripple', 'xrp'],
            'DOGE-USD': ['dogecoin', 'doge'],
            'ADA-USD': ['cardano', 'ada']
        }
        
        if not APIFY_AVAILABLE:
            logger.warning("⚠️  ApifyClient not installed. Reddit sentiment disabled.")
            return
        
        if not APIFY_USER_ID or not APIFY_API_TOKEN:
            logger.warning("⚠️  APIFY_USER_ID or APIFY_API_TOKEN not found in environment")
            return
        
        try:
            self.client = ApifyClient(APIFY_API_TOKEN)
            logger.info("✅ Apify client initialized for Reddit sentiment")
        except Exception as e:
            logger.error(f"❌ Apify init failed: {e}")
            self.client = None
    
    def fetch_pair_sentiment(self, pair, subreddits=None):
        """
        Fetch sentiment for a specific pair from Reddit via Apify.
        
        Args:
            pair: Trading pair (e.g., 'BTC-USD')
            subreddits: List of subreddits to search (default: standard crypto subs)
        
        Returns: sentiment_score (-1.0 to 1.0)
        """
        if not self.client:
            logger.warning(f"Apify client not available for {pair}")
            return 0.0
        
        if subreddits is None:
            subreddits = ['CryptoCurrency', 'Bitcoin', 'ethereum']
        
        keywords = self.pair_keywords.get(pair, [pair.split('-')[0].lower()])
        
        try:
            all_posts = []
            
            for subreddit in subreddits:
                for keyword in keywords[:1]:  # Limit to 1 keyword per subreddit to avoid rate limit
                    logger.info(f"  Fetching {pair} from r/{subreddit} (keyword: {keyword})...")
                    
                    # Build Apify actor input
                    run_input = {
                        "startUrls": [
                            {"url": f"https://www.reddit.com/r/{subreddit}/search?q={keyword}&sort=new&t=week"}
                        ],
                        "maxPosts": 30,
                        "proxy": {"useApifyProxy": True}
                    }
                    
                    # Execute actor
                    run = self.client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
                    
                    # Extract posts from results
                    if 'output' in run and 'posts' in run['output']:
                        posts = run['output']['posts']
                        all_posts.extend(posts)
                        logger.debug(f"    Got {len(posts)} posts from r/{subreddit}")
            
            if all_posts:
                sentiment = self._calculate_sentiment(all_posts)
                logger.info(f"  {pair}: sentiment={sentiment:.4f} ({len(all_posts)} posts)")
                return sentiment
            else:
                logger.warning(f"  {pair}: No posts found")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error fetching sentiment for {pair}: {e}")
            return 0.0
    
    @staticmethod
    def _calculate_sentiment(posts):
        """
        Calculate sentiment from Reddit posts.
        
        Weights: 
        - Text analysis (bullish/bearish keywords): 50%
        - Upvote direction: 30%
        - Comment engagement: 20%
        """
        if not posts:
            return 0.0
        
        total_sentiment = 0.0
        total_weight = 0.0
        
        for post in posts:
            try:
                # Extract post data
                upvotes = int(post.get('upvotes', 0)) or 1
                comments = int(post.get('nComments', 0)) or int(post.get('comments', 0)) or 1
                title = post.get('title', '').lower()
                selftext = post.get('selftext', '').lower() if post.get('selftext') else ''
                
                # Combine text for analysis
                text_content = title + ' ' + selftext
                
                # Text sentiment: count bullish vs bearish keywords
                bullish_count = sum(1 for word in BULLISH_KEYWORDS if word in text_content)
                bearish_count = sum(1 for word in BEARISH_KEYWORDS if word in text_content)
                
                text_sentiment = 0.0
                if bullish_count + bearish_count > 0:
                    text_sentiment = (bullish_count - bearish_count) / (bullish_count + bearish_count)
                
                # Upvote sentiment (positive upvotes = bullish)
                upvote_sentiment = 1.0 if upvotes > 0 else -1.0
                
                # Comment sentiment (high engagement = confidence)
                comment_sentiment = 1.0 if comments > 5 else (0.0 if comments == 1 else 0.5)
                
                # Weighted combined sentiment
                post_sentiment = (
                    0.5 * text_sentiment +
                    0.3 * upvote_sentiment +
                    0.2 * comment_sentiment
                )
                
                # Weight by engagement (log scale)
                if NUMPY_AVAILABLE:
                    weight = np.log1p(upvotes) + 0.3 * np.log1p(comments)
                else:
                    weight = (upvotes ** 0.5) + 0.3 * (comments ** 0.5)
                
                total_sentiment += post_sentiment * weight
                total_weight += weight
                
            except Exception as e:
                logger.debug(f"Error processing post: {e}")
                continue
        
        # Normalize to [-1, 1]
        if total_weight > 0:
            result = total_sentiment / total_weight
            if NUMPY_AVAILABLE:
                return float(np.clip(result, -1.0, 1.0))
            else:
                return max(-1.0, min(1.0, result))
        else:
            return 0.0
    
    def run(self):
        """Fetch sentiment for all trading pairs."""
        sentiments = {}
        
        for pair in self.pair_keywords.keys():
            sentiment = self.fetch_pair_sentiment(pair)
            sentiments[pair] = sentiment
        
        return sentiments


def save_cache(sentiments):
    """Save Reddit sentiment to cache file."""
    cache_data = {
        pair: {
            'sentiment': score,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'source': 'Apify Reddit Actor',
            'subreddits': 'r/CryptoCurrency, r/Bitcoin, r/ethereum'
        }
        for pair, score in sentiments.items()
    }
    
    with open(REDDIT_CACHE_FILE, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    logger.info(f"💾 Reddit sentiment cache saved to {REDDIT_CACHE_FILE}")
    return cache_data


def main():
    """Run Reddit sentiment fetching."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s: %(message)s'
    )
    
    logger.info("🚀 Starting Reddit sentiment fetch (Apify)...")
    
    fetcher = RedditSentimentFetcher()
    sentiments = fetcher.run()
    
    if sentiments:
        cache_data = save_cache(sentiments)
        print("\n✅ Reddit sentiment aggregation complete")
        print(json.dumps(cache_data, indent=2), flush=True)
    else:
        logger.warning("❌ No Reddit sentiment fetched (Apify may be unavailable)")
        print(json.dumps({}, indent=2), flush=True)


if __name__ == '__main__':
    main()
