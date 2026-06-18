#!/usr/bin/env python3
"""
Test script for new Apify Reddit scraper actors suggested by user.

Actors:
- scrapesmith/reddit-scraper (~$0.80 per 1000)
- solidcode/reddit-scraper (~$1.00 per 1000)

Last successful Reddit data from Apify was 2026-06-12 using the old actor.

This script tries several common input schemas used by Apify Reddit scrapers.
"""

import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
if not APIFY_TOKEN:
    print("❌ No APIFY_API_TOKEN in .env")
    exit(1)

try:
    from apify_client import ApifyClient
except ImportError:
    print("❌ apify-client not installed")
    exit(1)

client = ApifyClient(APIFY_TOKEN)

NEW_ACTORS = [
    ("scrapesmith/reddit-scraper", 0.80),
    ("solidcode/reddit-scraper", 1.00),
]

TEST_SUBREDDIT = "CryptoCurrency"
TEST_KEYWORD = "BTC"

def try_actor(actor_id, cost):
    print(f"\n{'='*55}")
    print(f"Actor: {actor_id} (~${cost}/1000)")
    print(f"{'='*55}")

    # Common input schemas for Apify Reddit scrapers
    variants = [
        ("search + subreddit", {
            "search": TEST_KEYWORD,
            "subreddit": TEST_SUBREDDIT,
            "maxPosts": 5,
            "sort": "new",
            "time": "week",
        }),
        ("startUrls", {
            "startUrls": [
                {"url": f"https://www.reddit.com/r/{TEST_SUBREDDIT}/search?q={TEST_KEYWORD}&sort=new&t=week"}
            ],
            "maxPosts": 5,
        }),
        ("queries", {
            "queries": [TEST_KEYWORD],
            "subreddits": [TEST_SUBREDDIT],
            "maxPostsPerQuery": 5,
            "sort": "new",
        }),
    ]

    for label, run_input in variants:
        print(f"  Variant: {label}")
        try:
            run = client.actor(actor_id).call(run_input=run_input)
            status = run.get("status")
            print(f"    Status: {status}")

            dataset_id = run.get("defaultDatasetId")
            items = []
            if dataset_id:
                items = client.dataset(dataset_id).list_items(limit=10).items

            if items:
                print(f"    ✅ SUCCESS: Got {len(items)} items")
                sample = items[0]
                print(f"    Sample keys: {list(sample.keys())[:8]}")
                if "title" in sample:
                    print(f"    Sample: {str(sample.get('title', ''))[:70]}")
                return True, items
            else:
                print("    No items (run succeeded but empty)")
        except Exception as e:
            print(f"    ❌ {type(e).__name__}: {str(e)[:130]}")

    return False, []

def main():
    print("Testing suggested Apify Reddit actors")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Test: keyword={TEST_KEYWORD} in r/{TEST_SUBREDDIT}\n")

    successes = []

    for actor_id, cost in NEW_ACTORS:
        worked, items = try_actor(actor_id, cost)
        if worked:
            successes.append((actor_id, cost, len(items)))

    print("\n=== RESULTS ===")
    if successes:
        print("Working actors:")
        for a, c, n in successes:
            print(f"  ✅ {a} (${c}/1000) — returned {n} posts in test")
        best = min(successes, key=lambda x: x[1])
        print(f"\nBest (cheapest): {best[0]}")
    else:
        print("No actors returned data with the tested input schemas.")
        print("Suggestions:")
        print("  1. Check the exact Input schema in the Apify Console for these actors")
        print("  2. Run a test directly in the Apify web UI first")
        print("  3. Look for other public Reddit scrapers (search 'reddit scraper' on Apify store)")

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tested": [a[0] for a in NEW_ACTORS],
        "working": [s[0] for s in successes],
        "recommendation": successes[0][0] if successes else None,
    }
    Path("data/state/apify_reddit_actor_test.json").parent.mkdir(parents=True, exist_ok=True)
    with open("data/state/apify_reddit_actor_test.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nReport saved to data/state/apify_reddit_actor_test.json")

if __name__ == "__main__":
    main()