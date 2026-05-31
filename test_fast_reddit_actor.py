#!/usr/bin/env python3
"""Full multi-pair test using fatihtahta/reddit-scraper-search-fast"""

import os
import json
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

PAIRS = {
    'BTC-USD': ['bitcoin'],
    'ETH-USD': ['ethereum'],
    'SOL-USD': ['solana'],
    'XRP-USD': ['ripple'],
    'DOGE-USD': ['dogecoin'],
}

SUBREDDITS = ['CryptoCurrency', 'Bitcoin', 'ethereum']

BULLISH = ['moon', 'pump', 'buy', 'bull', 'gain', 'surge', 'hodl', 'strong', 'opportunity']
BEARISH = ['crash', 'dump', 'sell', 'bear', 'loss', 'scam', 'rug', 'warning']

def fetch_posts(keyword, subreddit, max_posts=15):
    run_input = {
        "queries": [keyword],
        "subredditName": subreddit,
        "maxPosts": max_posts,
        "sort": "new",
        "timeframe": "week",
        "scrapeComments": False
    }
    run = client.actor("fatihtahta/reddit-scraper-search-fast").call(run_input=run_input)
    output = getattr(run, "output", {}) or {}
    return output.get("results", [])

def score_posts(posts):
    if not posts:
        return 0.0
    bull = bear = 0
    for p in posts:
        text = (p.get("title", "") + " " + (p.get("selftext") or "")).lower()
        bull += sum(1 for w in BULLISH if w in text)
        bear += sum(1 for w in BEARISH if w in text)
    total = bull + bear
    return (bull - bear) / total if total > 0 else 0.0

print("🚀 Running full sentiment test with fast Reddit actor...\n")
results = {}

for pair, keywords in PAIRS.items():
    all_posts = []
    for sub in SUBREDDITS:
        for kw in keywords:
            posts = fetch_posts(kw, sub)
            all_posts.extend(posts)
            print(f"{pair} | r/{sub} | {kw}: {len(posts)} posts")

    score = score_posts(all_posts)
    results[pair] = {
        "sentiment": round(score, 4),
        "posts": len(all_posts),
        "timestamp": "live"
    }
    print(f"→ {pair}: {score:.4f} ({len(all_posts)} total posts)\n")

print("\n=== FINAL REDDIT SENTIMENT RESULTS ===")
print(json.dumps(results, indent=2))