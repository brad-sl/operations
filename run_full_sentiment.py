#!/usr/bin/env python3
"""Full X + Reddit sentiment analysis with field normalization"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

PAIRS = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD']
KEYWORDS = {
    'BTC-USD': 'bitcoin',
    'ETH-USD': 'ethereum',
    'SOL-USD': 'solana',
    'XRP-USD': 'ripple',
    'DOGE-USD': 'dogecoin',
}

BULLISH = ['moon', 'pump', 'buy', 'bull', 'gain', 'surge', 'hodl', 'strong']
BEARISH = ['crash', 'dump', 'sell', 'bear', 'loss', 'scam', 'rug']

def normalize_post(post):
    if isinstance(post, str):
        return {"title": post, "selftext": "", "upvotes": 0, "nComments": 0}
    if not isinstance(post, dict):
        return {"title": "", "selftext": "", "upvotes": 0, "nComments": 0}
    return {
        "title": str(post.get("title") or post.get("postTitle") or ""),
        "selftext": str(post.get("selftext") or post.get("body") or ""),
        "upvotes": int(post.get("upvotes") or post.get("score") or 0),
        "nComments": int(post.get("nComments") or post.get("numComments") or 0),
    }

def fetch_reddit(keyword, max_posts=12):
    run_input = {
        "queries": [keyword],
        "subredditName": "CryptoCurrency",
        "maxPosts": max_posts,
        "sort": "new",
        "timeframe": "week",
        "scrapeComments": False
    }
    run = client.actor("fatihtahta/reddit-scraper-search-fast").call(run_input=run_input)
    output = getattr(run, "output", {}) or {}
    raw = output.get("results", [])
    return [normalize_post(p) for p in raw]

def score(posts):
    if not posts:
        return 0.0
    bull = bear = 0
    for p in posts:
        text = (p["title"] + " " + p["selftext"]).lower()
        bull += sum(1 for w in BULLISH if w in text)
        bear += sum(1 for w in BEARISH if w in text)
    total = bull + bear
    return round((bull - bear) / total, 4) if total > 0 else 0.0

print("=== Full Sentiment Analysis (Reddit + X) ===\n")
results = {}

for pair in PAIRS:
    kw = KEYWORDS[pair]
    reddit_posts = fetch_reddit(kw)
    reddit_score = score(reddit_posts)
    results[pair] = {
        "reddit": {"score": reddit_score, "posts": len(reddit_posts)},
        "x": {"score": 0.0, "posts": 0, "note": "X credentials need path fix"},
        "combined": round(reddit_score, 4),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    print(f"{pair}: Reddit={reddit_score} ({len(reddit_posts)} posts) | X=0.0 (auth path)")

print("\n" + json.dumps(results, indent=2))