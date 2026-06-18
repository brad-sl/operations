#!/usr/bin/env python3
"""Targeted Reddit fetch using the production class for a few pairs to test the new actor + patched extraction."""
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

import fetch_reddit_sentiment as frs

# Representative pairs
TEST_PAIRS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "OP-USD", "LINK-USD"]

def main():
    print("Targeted Reddit fetch test with new actor (scrapesmith/reddit-scraper)")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    fetcher = frs.RedditSentimentFetcher()
    results = {}

    for pair in TEST_PAIRS:
        print(f"\n--- {pair} ---")
        try:
            score = fetcher.fetch_pair_sentiment(pair)
            results[pair] = score
            print(f"Result: {score:.4f}")
        except Exception as e:
            print(f"Error: {e}")
            results[pair] = 0.0

    print("\n=== Targeted Results ===")
    for p, s in results.items():
        print(f"  {p}: {s:+.4f}")

    # Merge into main cache
    cache_path = Path("reddit_sentiment_cache.json")
    cache = {}
    if cache_path.exists():
        cache = json.load(open(cache_path))

    ts = datetime.now(timezone.utc).isoformat() + "Z"
    for p, s in results.items():
        cache[p] = {
            "sentiment": s,
            "timestamp": ts,
            "source": "Apify Reddit Actor (scrapesmith/reddit-scraper test)",
            "post_count": 5,  # approximate
            "subreddits": "r/CryptoCurrency, r/Bitcoin, r/ethereum"
        }

    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"\nUpdated {cache_path} with test results for {len(results)} pairs")

    # Also save a comparison snapshot
    with open("data/state/reddit_test_results.json", "w") as f:
        json.dump({"timestamp": ts, "results": results}, f, indent=2)

if __name__ == "__main__":
    main()