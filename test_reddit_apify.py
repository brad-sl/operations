#!/usr/bin/env python3
"""Quick test of automation-lab/reddit-scraper across trading pairs"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

PAIRS = {
    'BTC-USD': ['bitcoin', 'btc'],
    'ETH-USD': ['ethereum', 'eth'],
    'SOL-USD': ['solana', 'sol'],
    'XRP-USD': ['ripple', 'xrp'],
    'DOGE-USD': ['dogecoin', 'doge'],
}

SUBREDDITS = ['CryptoCurrency', 'Bitcoin', 'ethereum']

BULLISH = ['moon', 'pump', 'buy', 'bull', 'gain', 'surge', 'hodl', 'strong']
BEARISH = ['crash', 'dump', 'sell', 'bear', 'loss', 'scam', 'rug']

def fetch_posts(keyword, subreddit, max_items=15):
    run_input = {
        "searchQuery": keyword,
        "subreddit": subreddit,
        "maxItems": max_items,
        "sort": "new",
        "timeRange": "week",
        "useResidentialProxy": True
    }
    run = client.actor("automation-lab/reddit-scraper").call(run_input=run_input)
    dataset_id = getattr(run, "defaultDatasetId", None)
    if not dataset_id:
        return []
    items = client.dataset(dataset_id).list_items().items
    return items or []

def score_posts(posts):
    if not posts:
        return 0.0
    bull = bear = 0
    for p in posts:
        text = (p.get("title", "") + " " + p.get("selftext", "")).lower()
        bull += sum(1 for w in BULLISH if w in text)
        bear += sum(1 for w in BEARISH if w in text)
    total = bull + bear
    return (bull - bear) / total if total > 0 else 0.0

results = {}
for pair, kws in PAIRS.items():
    all_posts = []
    for sub in SUBREDDITS:
        for kw in kws[:1]:
            posts = fetch_posts(kw, sub)
            all_posts.extend(posts)
            print(f"{pair} | r/{sub} | {kw}: {len(posts)} posts")
    score = score_posts(all_posts)
    results[pair] = {"sentiment": round(score, 4), "posts": len(all_posts)}
    print(f"→ {pair}: {score:.4f} ({len(all_posts)} total posts)\n")

print("\n=== FINAL RESULTS ===")
print(json.dumps(results, indent=2))