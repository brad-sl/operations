#!/usr/bin/env python3
"""Production-ready sentiment using TwqHBuZZPHJxiQrTU with native fields"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

ACTOR_ID = "TwqHBuZZPHJxiQrTU"

PAIRS = {
    'BTC-USD': 'bitcoin',
    'ETH-USD': 'ethereum',
    'SOL-USD': 'solana',
    'XRP-USD': 'ripple',
    'DOGE-USD': 'dogecoin',
}

def fetch_sentiment(keyword, max_posts=15):
    """Use documented parameters for rich output with sentiment"""
    run_input = {
        "queries": [keyword],
        "subredditName": "CryptoCurrency",
        "sort": "relevance",
        "timeframe": "week",
        "scrapeComments": False,           # keep false for speed during testing
        "maxComments": 30,
        "includeNsfw": False,
        "strictSearch": False,
        "maxPosts": max_posts,
        "sentiment_analysis": True,
        "content_analysis": False,
        "maximize_coverage": False
    }
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    output = getattr(run, "output", {}) or {}
    return output.get("results", [])

def get_sentiment_score(item):
    if not isinstance(item, dict):
        return None
    
    # Best: normalized bounded score
    if "sentiment_score_normalized" in item:
        return float(item["sentiment_score_normalized"])
    if "sentiment_score" in item:
        return float(item["sentiment_score"])
    
    # Label fallback
    label = str(item.get("sentiment_label", "")).lower()
    mapping = {
        "positive": 0.8,
        "negative": -0.8,
        "mixed": 0.0,
        "neutral": 0.15,
        "uncertain": 0.0
    }
    return mapping.get(label)

def aggregate(items):
    scores = []
    for item in items:
        s = get_sentiment_score(item)
        if s is not None:
            scores.append(s)
    if not scores:
        return 0.0, len(items)
    return round(sum(scores) / len(scores), 4), len(items)

print("=== Full Sentiment Analysis (Native Actor Fields) ===\n")
results = {}

for pair, kw in PAIRS.items():
    items = fetch_sentiment(kw)
    score, count = aggregate(items)
    results[pair] = {
        "sentiment": score,
        "items": count,
        "actor": ACTOR_ID,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    print(f"{pair}: {score} ({count} items)")

print("\n" + json.dumps(results, indent=2))