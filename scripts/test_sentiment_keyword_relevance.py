#!/usr/bin/env python3
"""
Sentiment Keyword Relevance Experiment - Extended to Reddit (Apify)

Tests multiple keyword variants per trading pair on X (primary) and Reddit (secondary).

Focus: Not raw volume, but *strong signals useful for trading decisions*:
- Post volume (discussion level)
- Engagement (upvotes + comments as proxy for attention)
- Trading relevance (presence of price action, buy/sell, moon/pump/dump, ATH, dip language vs. pure news/company fluff)
- Sample titles for manual review of signal quality (trader talk vs noise)

Run: python3 scripts/test_sentiment_keyword_relevance.py

After Apify cost limit reset, this now exercises Reddit.

Real data only. Conservative limits on calls to control cost/rate.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import re

BASE_DIR = Path("/home/brad/projects/crypto-trading-bot")
ENV_FILE = BASE_DIR / ".env"

# Trading signal keywords (expanded from the production bullish/bearish lists)
TRADING_WORDS = [
    'price', 'buy', 'sell', 'moon', 'pump', 'dump', 'ath', 'dip', 'hold', 'hodl',
    'bull', 'bear', 'long', 'short', 'breakout', 'support', 'resistance', 'volume',
    'gain', 'loss', 'surge', 'crash', 'rally'
]

def load_env_var(name: str) -> str:
    if not ENV_FILE.exists():
        return ""
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    val = line.split("=", 1)[1].strip().strip('"\'')
                    return val
    except Exception:
        pass
    return ""

def load_bearer_token():
    return load_env_var("X_API_BEARER")

def load_apify_token():
    return load_env_var("APIFY_API_TOKEN")

def fetch_x_posts_for_test(bearer_token: str, query: str, max_results: int = 10):
    import requests
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": query + " -scam -is:retweet",
        "max_results": min(max_results, 10),
        "tweet.fields": "created_at,public_metrics",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ X API {resp.status_code}")
            return []
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  ⚠️ X error: {e}")
        return []

def count_trading_relevance(posts: list, is_reddit: bool = False) -> int:
    """Crude but useful proxy for trading signal strength."""
    count = 0
    for p in posts:
        text = ""
        if is_reddit:
            text = (p.get("title", "") + " " + p.get("selftext", "")).lower()
        else:
            text = p.get("text", "").lower()
        if any(word in text for word in TRADING_WORDS):
            count += 1
    return count

def test_x_keywords(bearer: str, pairs_and_variants: dict, max_results: int = 10):
    results = {}
    print("\n=== X (Twitter) Keyword Relevance Test ===\n")
    for pair, variants in pairs_and_variants.items():
        print(f"\n{pair}:")
        pair_results = {}
        for variant_name, query_term in variants.items():
            posts = fetch_x_posts_for_test(bearer, query_term, max_results)
            count = len(posts)
            trading = count_trading_relevance(posts, is_reddit=False)
            sample = posts[0].get("text", "")[:100].replace("\n", " ") if posts else "(no posts)"
            print(f"  {variant_name:20s} -> {count:3d} posts | trading_relevant: {trading:2d} | sample: {sample}")
            pair_results[variant_name] = {
                "count": count,
                "trading_relevant": trading,
                "query": query_term,
                "sample": sample,
            }
        results[pair] = pair_results
    return results

def test_reddit_keywords(apify_token: str, pairs_and_variants: dict, max_posts: int = 8):
    """Test Reddit via Apify for the same variants. Conservative to control cost."""
    try:
        from apify_client import ApifyClient
    except ImportError:
        print("apify_client not installed. Skipping Reddit.")
        return {}

    if not apify_token:
        print("No APIFY_API_TOKEN in .env. Skipping Reddit.")
        return {}

    client = ApifyClient(apify_token)
    REDDIT_ACTOR_ID = "wVnq9gKj7DKKZQqQe"
    SUBREDDITS = ["CryptoCurrency", "Bitcoin"]  # Focused, not the full 3 to save cost

    results = {}
    print("\n=== Reddit (Apify) Keyword Relevance Test ===\n")

    for pair, variants in pairs_and_variants.items():
        print(f"\n{pair}:")
        pair_results = {}
        for variant_name, keyword in variants.items():
            all_posts = []
            for subreddit in SUBREDDITS:
                try:
                    run_input = {
                        "startUrls": [
                            {"url": f"https://www.reddit.com/r/{subreddit}/search?q={keyword}&sort=new&t=week"}
                        ],
                        "maxPosts": max_posts,
                        "proxy": {"useApifyProxy": True},
                    }
                    run = client.actor(REDDIT_ACTOR_ID).call(run_input=run_input)
                    if "output" in run and "posts" in run["output"]:
                        posts = run["output"]["posts"]
                        all_posts.extend(posts)
                except Exception as e:
                    print(f"    ⚠️ Apify error on {subreddit}/{keyword}: {str(e)[:80]}")

            count = len(all_posts)
            trading = count_trading_relevance(all_posts, is_reddit=True)
            avg_upvotes = sum(int(p.get("upvotes", 0) or 0) for p in all_posts) / max(1, count) if count else 0
            avg_comments = sum(int(p.get("nComments", 0) or p.get("comments", 0) or 0) for p in all_posts) / max(1, count) if count else 0

            sample_title = all_posts[0].get("title", "")[:90] if all_posts else "(no posts)"
            print(f"  {variant_name:20s} -> {count:2d} posts | trading_relevant: {trading:2d} | avg_up={avg_upvotes:.1f} avg_com={avg_comments:.1f}")
            print(f"    sample: {sample_title}")

            pair_results[variant_name] = {
                "count": count,
                "trading_relevant": trading,
                "avg_upvotes": round(avg_upvotes, 1),
                "avg_comments": round(avg_comments, 1),
                "sample": sample_title,
                "keyword_used": keyword,
            }
        results[pair] = pair_results
    return results

def main():
    print("Sentiment Keyword Relevance Experiment (X + Reddit)")
    print(f"Time: {datetime.utcnow().isoformat()}")
    print("Goal: Identify keywords that produce *strong, tradable signals* (price action, trader discussion) vs noise.")

    bearer = load_bearer_token()
    apify_token = load_apify_token()

    # Same focused test pairs as before
    test_pairs = ["XRP-USD", "BTC-USD", "ARB-USD"]

    variants = {
        "XRP-USD": {
            "XRP (ticker)": "XRP",
            "xrp (lower)": "xrp",
            "ripple (old)": "ripple",
            "$XRP (dollar)": "$XRP",
        },
        "BTC-USD": {
            "BTC (ticker)": "BTC",
            "bitcoin (name)": "bitcoin",
            "BTC OR bitcoin": "BTC OR bitcoin",
            "$BTC": "$BTC",
        },
        "ARB-USD": {
            "ARB (ticker)": "ARB",
            "arbitrum (name)": "arbitrum",
            "ARB OR arbitrum": "ARB OR arbitrum",
            "$ARB": "$ARB",
        },
    }

    pairs_and_variants = {p: variants[p] for p in test_pairs if p in variants}

    x_results = {}
    if bearer:
        x_results = test_x_keywords(bearer, pairs_and_variants, max_results=10)
    else:
        print("No X bearer — skipping X test.")

    reddit_results = {}
    if apify_token:
        reddit_results = test_reddit_keywords(apify_token, pairs_and_variants, max_posts=8)
    else:
        print("No Apify token — skipping Reddit test.")

    # Combined summary focused on signal quality
    print("\n=== SIGNAL QUALITY SUMMARY ===")
    print("Higher 'trading_relevant' count + engagement = better for trading decisions (price action, conviction).")
    print("Raw volume alone is secondary.\n")

    for pair in test_pairs:
        print(f"\n{pair}:")
        if pair in x_results:
            x_best = max(x_results[pair].items(), key=lambda item: (item[1]["trading_relevant"], item[1]["count"]))
            print(f"  X best: {x_best[0]} (trading_relevant={x_best[1]['trading_relevant']}, posts={x_best[1]['count']})")
        if pair in reddit_results:
            r_best = max(reddit_results[pair].items(), key=lambda item: (item[1]["trading_relevant"], item[1]["count"], item[1]["avg_upvotes"]))
            print(f"  Reddit best: {r_best[0]} (trading_relevant={r_best[1]['trading_relevant']}, posts={r_best[1]['count']}, avg_up={r_best[1]['avg_upvotes']})")

    # Save everything
    out_path = BASE_DIR / "data" / "state" / "keyword_relevance_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "focus": "Strong trading signals (price action / trader conviction) vs noise",
            "x_results": x_results,
            "reddit_results": reddit_results,
            "note": "trading_relevant = posts containing price/buy/sell/moon/pump/dump/ath/dip/hold etc. Use samples for qualitative review."
        }, f, indent=2)
    print(f"\nFull results (X + Reddit) saved to {out_path}")

    print("\nNext: Review the samples. If Reddit strongly prefers tickers (especially for XRP), we can lock the maps and re-run production fetches.")

if __name__ == "__main__":
    main()