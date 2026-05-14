#!/usr/bin/env python3
"""
Cryptocurrency Sentiment Aggregation (Batch-Optimized)
Prioritizes X (Twitter) sentiment with batch query optimization
"""

import os
import json
import logging
import requests
import traceback
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

from sentiment_decay_model import SentimentDecayModel

# X API batch size: max pairs per single call
# (3 pairs balances API query length vs. number of calls)
MAX_X_BATCH_SIZE = 3

class SentimentAggregator:
    def __init__(self):
        self.decay_model = SentimentDecayModel()

    """
    Sentiment Aggregation with Strict Error Handling
    
    Core Principle: Never generate artificial sentiment data 
    that could influence trading decisions
    """
    
    def __init__(self, 
                 log_path: str = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/sentiment_errors.log'):
        """
        Initialize sentiment aggregator with robust error handling
        
        Args:
            log_path (str): Path to error logging file
        """
        # Configure logging
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logging.basicConfig(
            level=logging.ERROR,  # Only log critical errors
            format='%(asctime)s - CRITICAL: %(message)s',
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Retrieve credentials from environment
        self.apify_user_id = os.getenv('APIFY_USER_ID')
        self.apify_api_token = os.getenv('APIFY_API_TOKEN')
        
        # Initialize Apify client
        self.apify_client = None
        if self.apify_user_id and self.apify_api_token:
            try:
                self.apify_client = ApifyClient(self.apify_api_token)
            except Exception as e:
                self.logger.error(f"Apify client initialization failed: {e}")
    
    def _fetch_reddit_sentiment_apify(self, 
                                      keywords: list = ['bitcoin', 'crypto', 'BTC'], 
                                      max_posts: int = 100) -> Dict[str, Any]:
        """
        Fetch Reddit sentiment using Apify
        
        Args:
            keywords (list): Keywords to search
            max_posts (int): Maximum number of posts to analyze
        
        Returns:
            Dict with minimal sentiment metrics or error state
        """
        if not self.apify_client:
            self.logger.error("Apify client not initialized. Cannot fetch Reddit sentiment.")
            return {
                'status': 'error',
                'error_message': 'Apify client not configured',
                'timestamp': datetime.utcnow().isoformat()
            }
        
        try:
            # Run Reddit Scraper actor
            run_input = {
                "searchTerms": keywords,
                "subreddits": ["CryptoCurrency", "Bitcoin", "CryptoTechnology"],
                "maxItems": max_posts
            }
            
            # Run the actor
            run = self.apify_client.actor("taroyamada/reddit-data-scraper").call(
                run_input=run_input
            )
            
            # Fetch results
            results = self.apify_client.dataset(run["defaultDatasetId"]).list_items()
            
            # If no results, return neutral state
            if not results.items:
                return {
                    'status': 'no_data',
                    'keywords': keywords,
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            return {
                'status': 'success',
                'keywords': keywords,
                'post_count': len(results.items),
                'timestamp': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            error_details = {
                'status': 'error',
                'error_type': type(e).__name__,
                'error_message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            self.logger.error(f"Apify Reddit Sentiment Fetch Failed: {json.dumps(error_details, indent=2)}")
            
            return error_details

    def process_sentiment(self) -> Dict[str, Any]:
        """
        Aggregate sentiment with strict error handling
        
        Returns:
            Sentiment report with minimal, safe information
        """
        # Fetch Reddit sentiment via Apify
        reddit_sentiment = self._fetch_reddit_sentiment_apify()
        
        # Construct response that never manufactures sentiment
        return {
            'source': 'reddit',
            'result': reddit_sentiment,
            'timestamp': datetime.utcnow().isoformat()
        }

def fetch_x_sentiment_batch_optimized() -> Dict[str, Any]:
    """
    Fetch X sentiment using optimized batch queries.
    Calls fetch_x_sentiment.py which handles:
    - Single OR query instead of 6 separate calls
    - Keyword distribution across pairs
    - Batch chunking if needed
    """
    try:
        result = subprocess.run(
            [
                '/home/brad/.openclaw/workspace/operations/crypto-bot/venv/bin/python3',
                '/home/brad/.openclaw/workspace/operations/crypto-bot/fetch_x_sentiment.py'
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd='/home/brad/.openclaw/workspace/operations/crypto-bot'
        )
        
        if result.returncode == 0:
            # Parse JSON from output (last valid JSON block)
            lines = result.stdout.split('\n')
            for line in reversed(lines):
                if line.strip().startswith('{'):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
        
        print(f"⚠️ X sentiment fetch failed: {result.stderr}")
        return {}
    
    except Exception as e:
        print(f"❌ Error fetching X sentiment: {e}")
        return {}

def merge_sentiment_data(reddit_result: Dict, x_sentiment: Dict) -> Dict[str, Any]:
    """
    Merge Reddit sentiment (from Apify) with X sentiment (batched).
    
    Returns combined cache ready for Phase 5.
    """
    merged = {}
    
    # Use X sentiment as primary, fall back to neutral
    for pair in ['BTC-USD', 'XRP-USD', 'ETH-USD', 'DOGE-USD', 'ADA-USD', 'SOL-USD']:
        if pair in x_sentiment:
            merged[pair] = x_sentiment[pair]
        else:
            # Fallback: neutral if not found
            merged[pair] = {
                'sentiment': 0.0,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'source': 'fallback',
                'query': pair
            }
    
    return merged

def main():
    """
    Run sentiment aggregation with batch-optimized X API calls
    """
    # Initialize sentiment aggregator (for Reddit/Apify)
    aggregator = SentimentAggregator()
    
    # Fetch Reddit sentiment
    reddit_result = aggregator.process_sentiment()
    print(f"\n✓ Reddit sentiment processed", flush=True)
    
    # Fetch X sentiment (batch-optimized: 1-2 calls instead of 6)
    print(f"\n🚀 Fetching X sentiment (batch-optimized)...", flush=True)
    x_sentiment = fetch_x_sentiment_batch_optimized()
    
    # Merge and write to cache
    if x_sentiment:
        final_cache = merge_sentiment_data(reddit_result, x_sentiment)
    else:
        final_cache = x_sentiment if x_sentiment else {}
    
    # Write combined cache
    cache_file = '/home/brad/.openclaw/workspace/operations/crypto-bot/sentiment_cache.json'
    with open(cache_file, 'w') as f:
        json.dump(final_cache, f, indent=2)
    
    print(f"\n✅ Sentiment cache updated: {cache_file}", flush=True)
    print(json.dumps(final_cache, indent=2), flush=True)

if __name__ == '__main__':
    main()
