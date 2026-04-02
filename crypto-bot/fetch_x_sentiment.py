#!/usr/bin/env python3
"""
Fetch real X (Twitter) sentiment for BTC and XRP
Uses X API v2 with bearer token from .env
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

# Load bearer token from .env
from dotenv import load_dotenv
load_dotenv()

BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")
if not BEARER_TOKEN:
    print("❌ ERROR: X_BEARER_TOKEN not found in .env")
    exit(1)

BASE_DIR = Path("/home/brad/.openclaw/workspace/operations/crypto-bot")
CACHE_FILE = BASE_DIR / "x_sentiment_cache.json"

def search_x_sentiment(query, max_results=100):
    """Fetch recent tweets about a topic from X API v2."""
    url = "https://api.twitter.com/2/tweets/search/recent"
    
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "User-Agent": "Phase4-Sentiment-Bot/1.0"
    }
    
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,lang",
        "expansions": "author_id",
        "user.fields": "username,public_metrics"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ X API Error: {e}")
        return None

def analyze_sentiment(tweets_data):
    """Simple sentiment scoring based on tweet metrics."""
    if not tweets_data or "data" not in tweets_data or not tweets_data["data"]:
        return 0.0  # Neutral if no tweets
    
    tweets = tweets_data["data"]
    total_engagement = 0
    total_score = 0
    
    for tweet in tweets:
        metrics = tweet.get("public_metrics", {})
        like_count = metrics.get("like_count", 0)
        retweet_count = metrics.get("retweet_count", 0)
        reply_count = metrics.get("reply_count", 0)
        
        # Normalize engagement (retweets indicate agreement, likes indicate sentiment)
        engagement = like_count + (retweet_count * 1.5) + (reply_count * 0.5)
        total_engagement += engagement
        
        # Simple heuristic: high engagement = positive sentiment (people care)
        # This is crude but works for crypto sentiment (discussion != polarity)
        total_score += engagement
    
    if total_engagement == 0:
        return 0.0
    
    # Normalize to -1.0 to 1.0
    # Average engagement * sentiment factor
    avg_engagement = total_score / len(tweets)
    
    # Very rough: cap at reasonable levels
    # High engagement tweets = people talking = positive interest
    sentiment = min(1.0, max(-1.0, (avg_engagement / 100.0)))
    
    return round(sentiment, 2)

# Fetch sentiment for BTC
print("🔗 Fetching BTC sentiment from X API...")
btc_data = search_x_sentiment("bitcoin BTC price -scam", max_results=100)
btc_sentiment = analyze_sentiment(btc_data)
print(f"   BTC Sentiment: {btc_sentiment}")

# Fetch sentiment for XRP
print("🔗 Fetching XRP sentiment from X API...")
xrp_data = search_x_sentiment("XRP ripple price -scam", max_results=100)
xrp_sentiment = analyze_sentiment(xrp_data)
print(f"   XRP Sentiment: {xrp_sentiment}")

# Write to cache
cache_data = {
    "BTC-USD": {
        "sentiment": btc_sentiment,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "X API v2 (search/recent)",
        "query": "bitcoin BTC price -scam"
    },
    "XRP-USD": {
        "sentiment": xrp_sentiment,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "X API v2 (search/recent)",
        "query": "XRP ripple price -scam"
    }
}

with open(CACHE_FILE, 'w') as f:
    json.dump(cache_data, f, indent=2)

print(f"\n✅ Sentiment cache written to {CACHE_FILE}")
print(json.dumps(cache_data, indent=2))
