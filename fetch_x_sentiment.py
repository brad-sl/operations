#!/usr/bin/env python3
"""
Fetch real X (Twitter) sentiment for all Phase 5 trading pairs
Uses X API v2 with Bearer token - scalable combined query (Grok-optimized)
Handles dozens/hundreds of pairs efficiently with a single API call
"""

import requests
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from typing import List, Dict, Any, Optional

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    TextBlob = None

BASE_DIR = Path("/home/brad/.openclaw/workspace/operations/crypto-bot")
CACHE_FILE = BASE_DIR / "sentiment_cache.json"

def load_bearer_token():
    """Load X API Bearer token from .env (more robust parsing)"""
    env_file = BASE_DIR / ".env"

    if not env_file.exists():
        print("❌ ERROR: .env file not found")
        return None

    token = None
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"\'')
                if k == "X_API_BEARER":
                    token = unquote(v)
                    break
    except Exception as e:
        print(f"Error reading .env: {e}")
        return None

    return token if token else None

def fetch_x_posts_for_sentiment_analysis(
    bearer_token: str,
    keywords: List[str],
    max_results: int = 100,
    language: Optional[str] = "en"
) -> List[Dict[str, Any]]:
    """
    Fetches recent X posts matching a set of keywords using Bearer token authentication.
    Scalable combined query - handles dozens or hundreds of pairs efficiently.
    
    Returns a clean list of posts optimized for sentiment analysis (text + metadata).
    
    Args:
        bearer_token: X API v2 Bearer token
        keywords: List of keywords (e.g., ["BTC", "ETH", "SOL"])
        max_results: Max posts to fetch (1-100)
        language: Language filter (default "en")
    
    Returns:
        List of processed posts with text, metrics, author info
    """
    if not keywords:
        raise ValueError("Keywords list cannot be empty")
    
    # Build query: e.g., "BTC OR ETH OR SOL -scam lang:en -is:retweet"
    # Quotes added automatically for multi-word keywords
    query_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
    query = " OR ".join(query_parts)
    
    # Add filters
    query += " -scam -is:retweet"
    if language:
        query += f" lang:{language}"
    
    url = "https://api.twitter.com/2/tweets/search/recent"
    
    headers = {
        "Authorization": f"Bearer {bearer_token}"
    }
    
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,author_id,lang,public_metrics,context_annotations",
        "expansions": "author_id",
        "user.fields": "username,verified"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            error_detail = response.json() if response.content else response.text
            raise Exception(
                f"X API request failed with status {response.status_code}. "
                f"Error: {error_detail}"
            )
        
        data = response.json()
        
        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {user["id"]: user for user in includes.get("users", [])}
        
        # Process into clean format ideal for sentiment analysis
        processed_posts = []
        for tweet in tweets:
            author = users.get(tweet.get("author_id"), {})
            processed_posts.append({
                "id": tweet["id"],
                "text": tweet.get("text", ""),
                "created_at": tweet.get("created_at"),
                "author_id": tweet.get("author_id"),
                "author_username": author.get("username"),
                "author_verified": author.get("verified", False),
                "language": tweet.get("lang"),
                "public_metrics": tweet.get("public_metrics", {}),
                "context_annotations": tweet.get("context_annotations", []),
            })
        
        return processed_posts
    
    except Exception as e:
        print(f"⚠️ X API Error: {e}")
        return []

def distribute_posts_to_pairs(posts: List[Dict], keywords: Dict[str, str]) -> Dict[str, List[Dict]]:
    """
    Distribute posts to individual pairs based on keyword matching.
    
    Args:
        posts: List of processed posts from X API
        keywords: Dict of {pair: keyword} (e.g., {"BTC-USD": "BTC"})
    
    Returns:
        Dict of {pair: [posts_list]}
    """
    pair_posts = {pair: [] for pair in keywords.keys()}
    
    for post in posts:
        text = post["text"].lower()
        
        for pair, keyword in keywords.items():
            keyword_lower = keyword.lower()
            if keyword_lower in text:
                pair_posts[pair].append(post)
    
    return pair_posts

def analyze_sentiment(text: str) -> float:
    """
    Calculate sentiment polarity using TextBlob.
    Restored from archived implementation.
    Returns polarity in range [-1.0, 1.0]
    """
    if not TEXTBLOB_AVAILABLE or not text:
        return 0.0
    try:
        return float(TextBlob(text).sentiment.polarity)
    except Exception:
        return 0.0


def calculate_sentiment(posts: List[Dict]) -> float:
    """
    Calculate sentiment from posts based on public metrics + TextBlob polarity.
    
    Args:
        posts: List of posts with public_metrics and text
    
    Returns:
        Sentiment score (-1.0 to 1.0)
    """
    if not posts:
        return 0.0
    
    total_engagement = 0
    sentiment_score = 0
    
    total_polarity = 0.0
    posts_with_text = 0
    
    for post in posts:
        metrics = post.get("public_metrics", {})
        like_count = metrics.get("like_count", 0)
        retweet_count = metrics.get("retweet_count", 0)
        reply_count = metrics.get("reply_count", 0)
        text = post.get("text", "")
        
        # Engagement-based sentiment: retweets+replies indicate agreement/interest
        engagement = like_count + (retweet_count * 1.5) + (reply_count * 0.5)
        total_engagement += engagement
        sentiment_score += engagement
        
        # TextBlob polarity analysis (restored)
        if text:
            polarity = analyze_sentiment(text)
            total_polarity += polarity
            posts_with_text += 1
    
    if total_engagement == 0 and posts_with_text == 0:
        return 0.0
    
    # Calculate engagement-based component
    engagement_component = 0.0
    if total_engagement > 0:
        avg_engagement = sentiment_score / len(posts)
        engagement_component = max(-1.0, min(1.0, avg_engagement / 1000.0))
    
    # Calculate TextBlob polarity component
    polarity_component = 0.0
    if posts_with_text > 0:
        polarity_component = total_polarity / posts_with_text
    
    # Hybrid: 50% engagement, 50% TextBlob polarity (when both available)
    if total_engagement > 0 and posts_with_text > 0:
        final_score = 0.5 * engagement_component + 0.5 * polarity_component
    elif posts_with_text > 0:
        final_score = polarity_component
    else:
        final_score = engagement_component
    
    return max(-1.0, min(1.0, final_score))

def main():
    """Fetch X sentiment for all pairs and save to cache."""
    pairs = ["BTC-USD", "ETH-USD", "ADA-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
    
    # Map pairs to their X keywords
    keywords_dict = {
        pair: pair.split('-')[0]  # BTC-USD → BTC, ETH-USD → ETH, etc.
        for pair in pairs
    }
    
    bearer_token = load_bearer_token()
    if not bearer_token:
        print("❌ ERROR: X Bearer Token not found in .env")
        # Save neutral cache
        cache = {pair: {"sentiment": 0.0} for pair in pairs}
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        return
    
    print(f"🔍 Fetching X sentiment for {len(pairs)} pairs (combined query)...")
    
    # Single combined API call for all pairs
    keywords = [pair.split('-')[0] for pair in pairs]
    posts = fetch_x_posts_for_sentiment_analysis(
        bearer_token=bearer_token,
        keywords=keywords,
        max_results=100,
        language="en"
    )
    
    print(f"  Got {len(posts)} total posts from X API")
    
    # Distribute posts to individual pairs
    pair_posts = distribute_posts_to_pairs(posts, keywords_dict)
    
    # Calculate sentiment for each pair
    all_sentiments = {}
    for pair in pairs:
        posts_for_pair = pair_posts[pair]
        sentiment = calculate_sentiment(posts_for_pair)
        all_sentiments[pair] = sentiment
        print(f"  {pair}: {sentiment:.6f} ({len(posts_for_pair)} posts)")
    
    # Save to cache
    timestamp = datetime.utcnow().isoformat()
    cache = {
        pair: {
            "sentiment": all_sentiments.get(pair, 0.0),
            "timestamp": timestamp
        }
        for pair in pairs
    }
    
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)
    
    print(f"✅ X sentiment cached ({len(posts)} posts analyzed)")
    print(json.dumps(all_sentiments, indent=2))

if __name__ == "__main__":
    main()

def fetch_x_sentiment_apify(query: str = "bitcoin OR ethereum OR solana OR dogecoin OR xrp", max_items: int = 50) -> Dict[str, float]:
    """Fetch X sentiment using Apify Twitter Search Scraper as fallback."""
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("⚠️ apify_client not installed. Skipping Apify X fetch.")
        return {}

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("⚠️ No APIFY_API_TOKEN found")
        return {}

    client = ApifyClient(token)

    run_input = {
        "searchTerms": [query],
        "maxItems": max_items,
        "sort": "Latest",
    }

    try:
        run = client.actor("apify/twitter-search-scraper").call(run_input=run_input)
        dataset = client.dataset(run["defaultDatasetId"])
        items = list(dataset.iterate_items())

        # Very basic sentiment (count positive/negative keywords as proxy)
        scores = {}
        positive_words = {"bullish", "moon", "buy", "up", "good", "great", "pump"}
        negative_words = {"bearish", "dump", "sell", "down", "bad", "crash", "scam"}

        for item in items:
            text = (item.get("text") or "").lower()
            pos = sum(1 for w in positive_words if w in text)
            neg = sum(1 for w in negative_words if w in text)
            if pos > neg:
                scores["sentiment"] = scores.get("sentiment", 0) + 0.1
            elif neg > pos:
                scores["sentiment"] = scores.get("sentiment", 0) - 0.1

        avg = scores.get("sentiment", 0.0) / max(len(items), 1)
        print(f"✅ Apify X: analyzed {len(items)} posts, avg sentiment ≈ {avg:.2f}")
        return {"X_SENTIMENT": round(avg, 3)}
    except Exception as e:
        print(f"⚠️ Apify X failed: {e}")
        return {}

