#!/usr/bin/env python3
"""Full sentiment analysis using new actor TwqHBuZZPHJxiQrTU with built-in sentiment"""

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

def fetch_with_sentiment(keyword, max_posts=20):
    run_input = {
        "queries": [keyword],
        "subredditName": "CryptoCurrency",
        "sort": "relevance",
        "timeframe": "week",
        "scrapeComments": False,
        "maxComments": 30,
        "includeNsfw": False,
        "strictSearch": False,
        "maxPosts": max_posts,
        "sentiment_analysis": True,
        "content_analysis": False
    }
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    output = getattr(run, "output", {}) or {}
    return output.get("results", [])

def score_from_labels(posts):
    """Use sentiment_label from the actor when available"""
    if not posts:
        return 0.0
    
    scores = []
    for p in posts:
        if isinstance(p, str):
            continue
        label = p.get("sentiment_label", "").lower()
        if label == "positive":
            scores.append(0.8)
        elif label == "negative":
            scores.append(-0.8)
        elif label == "mixed":
            scores.append(0.0)
        elif label == "neutral":
            scores.append(0.1)
        elif label == "uncertain":
            scores.append(0.0)
        else:
            # fallback to simple keyword if no label
            text = str(p.get("title", "")).lower()
            if any(w in text for w in ["moon", "pump", "bull", "buy"]):
                scores.append(0.5)
            elif any(w in text for w in ["crash", "dump", "bear", "scam"]):
                scores.append(-0.5)
    
    return round(sum(scores) / len(scores), 4) if scores else 0.0

print("=== Full Sentiment Analysis (New Actor with Built-in Sentiment) ===\n")
results = {}

for pair, kw in PAIRS.items():
    posts = fetch_with_sentiment(kw)
    score = score_from_labels(posts)
    results[pair] = {
        "sentiment": score,
        "posts": len(posts),
        "actor": ACTOR_ID,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    print(f"{pair}: {score} ({len(posts)} posts)")

print("\n" + json.dumps(results, indent=2))