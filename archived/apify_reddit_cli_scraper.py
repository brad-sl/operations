#!/usr/bin/env python3
"""
Reddit Data Retrieval using Apify Client
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
from dotenv import load_dotenv
from apify_client import ApifyClient
from textblob import TextBlob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('/home/brad/.openclaw/workspace/operations/crypto-bot/logs/reddit_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def analyze_sentiment(text: str) -> float:
    """
    Calculate sentiment using TextBlob
    """
    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0

def main():
    # Load environment variables
    load_dotenv()
    
    # Get Apify API token
    api_token = os.getenv('APIFY_API_TOKEN')
    if not api_token:
        raise ValueError("APIFY_API_TOKEN not found in environment variables")
    
    # Initialize Apify client
    client = ApifyClient(api_token)
    
    try:
        # Cryptocurrency subreddits to crawl
        subreddits = [
            "r/CryptoCurrency",
            "r/Bitcoin", 
            "r/CryptoTechnology",
            "r/ethtrader"
        ]
        
        # Prepare the Actor input
        run_input = {
            "startUrls": [{"url": f"https://www.reddit.com/{subreddit}/top/"} for subreddit in subreddits],
            "searches": ["bitcoin", "ethereum", "crypto trading", "blockchain"],
            "sort": "top",
            "time": "week",
            "maxItems": 100,
            "maxPostCount": 50,
            "maxComments": 20,
            "scrollTimeout": 60,
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
            },
            "debugMode": True
        }
        
        logger.info("Starting Reddit data retrieval")
        
        # Run the Actor and wait for it to finish
        run = client.actor("trudax/reddit-scraper-lite").call(run_input=run_input)
        
        logger.info(f"💾 Dataset available at: https://console.apify.com/storage/datasets/{run['defaultDatasetId']}")
        
        # Retrieve and process items
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        
        # Basic sentiment analysis
        sentiments = []
        processed_items = []
        
        for item in items:
            # Extract text for sentiment analysis
            text = item.get('title', '') + ' ' + item.get('text', '')
            
            # Calculate sentiment
            sentiment = analyze_sentiment(text)
            sentiments.append(sentiment)
            
            # Prepare processed item
            processed_item = {
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'subreddit': item.get('subreddit', ''),
                'sentiment_score': sentiment
            }
            processed_items.append(processed_item)
        
        # Sentiment summary
        sentiment_summary = {
            'total_items': len(items),
            'avg_sentiment': sum(sentiments) / len(sentiments) if sentiments else 0,
            'sentiment_distribution': {
                'very_negative': sum(1 for s in sentiments if s <= -0.6),
                'negative': sum(1 for s in sentiments if -0.6 < s <= -0.2),
                'neutral': sum(1 for s in sentiments if abs(s) <= 0.2),
                'positive': sum(1 for s in sentiments if 0.2 < s <= 0.6),
                'very_positive': sum(1 for s in sentiments if s > 0.6)
            }
        }
        
        # Save results
        results_path = '/home/brad/.openclaw/workspace/operations/crypto-bot/logs/reddit_scrape_results.json'
        with open(results_path, 'w') as f:
            json.dump({
                'raw_items': items,
                'processed_items': processed_items,
                'sentiment_summary': sentiment_summary
            }, f, indent=2)
        
        logger.info(f"Results saved to {results_path}")
        logger.info(f"Sentiment Summary: {json.dumps(sentiment_summary, indent=2)}")
        
    except Exception as e:
        logger.error(f"Error during Reddit scraping: {e}")
        raise

if __name__ == '__main__':
    main()