#!/usr/bin/env python3
"""
Phase 6 - X (Twitter) Sentiment Fetcher
Ported and adapted from Phase 4/5 (fetch_x_sentiment.py)
- Separate module (X only)
- 30-minute frequency target (expensive API)
- Outputs cache with timestamp for 15-minute half-life decay + 2h staleness zeroing in scorer (t_ceb0da78)
- Paths updated for Phase 6 structure
"""

import requests
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from typing import List, Dict, Any, Optional

from textblob import TextBlob

# Phase 6 paths
PHASE6_DIR = Path("/home/brad/projects/crypto-trading-bot/phase6")
DATA_DIR = PHASE6_DIR / "data" / "sentiment"
CACHE_FILE = DATA_DIR / "x_sentiment_cache.json"
ENV_FILE = PHASE6_DIR / ".env"   # or fall back to project root .env

DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_bearer_token():
    """Load X API Bearer token from .env (robust parsing)"""
    candidates = [
        ENV_FILE,
        Path("/home/brad/projects/crypto-trading-bot/.env"),
        Path.home() / ".env"
    ]

    for env_file in candidates:
        if not env_file.exists():
            continue
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip('\"\'')
                    if k == "X_API_BEARER":
                        return unquote(v)
        except Exception as e:
            print(f"Error reading {env_file}: {e}")
            continue

    print("❌ ERROR: X_API_BEARER not found in any .env")
    return None


def fetch_x_posts_for_sentiment_analysis(
    bearer_token: str,
    keywords: List[str],
    max_results: int = 100,
    language: Optional[str] = "en"
) -> List[Dict[str, Any]]:
    """
    Fetches recent X posts matching keywords using Bearer token.
    Scalable combined query for multiple pairs.
    """
    if not keywords:
        raise ValueError("Keywords list cannot be empty")

    query_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
    query = " OR ".join(query_parts)
    query += " -scam -is:retweet"
    if language:
        query += f" lang:{language}"

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,author_id,lang,public_metrics,context_annotations",
        "expansions": "author_id",
        "user.fields": "username,verified"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            error_detail = response.json() if response.content else response.text
            raise Exception(f"X API failed {response.status_code}: {error_detail}")

        data = response.json()
        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {user["id"]: user for user in includes.get("users", [])}

        processed = []
        for tweet in tweets:
            author = users.get(tweet.get("author_id"), {})
            processed.append({
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
        return processed

    except Exception as e:
        print(f"⚠️ X API Error: {e}")
        return []


def distribute_posts_to_pairs(posts: List[Dict], keywords: Dict[str, str]) -> Dict[str, List[Dict]]:
    """Distribute posts to pairs based on keyword match."""
    pair_posts = {pair: [] for pair in keywords.keys()}
    for post in posts:
        text = post["text"].lower()
        for pair, keyword in keywords.items():
            if keyword.lower() in text:
                pair_posts[pair].append(post)
    return pair_posts


def calculate_sentiment(posts: List[Dict]) -> float:
    """
    Calculate sentiment using TextBlob polarity analysis on post text.
    Returns average polarity in [-1.0, 1.0].
    Falls back to 0.0 on errors (matches Phase 4 archived implementation).
    Engagement metrics are available but not used for primary scoring
    (restored to original TextBlob behavior per handoff).
    """
    if not posts:
        return 0.0

    polarities = []
    for post in posts:
        text = post.get("text", "")
        if not text or not text.strip():
            continue
        try:
            polarity = TextBlob(text).sentiment.polarity
            polarities.append(polarity)
        except Exception:
            # Graceful fallback as in archived Phase 4 code
            continue

    if not polarities:
        return 0.0

    avg_polarity = sum(polarities) / len(polarities)
    return max(-1.0, min(1.0, avg_polarity))


def main():
    """Fetch X sentiment for configured pairs and cache with timestamp."""
    # TODO: Load pairs from Phase 6 config (for now use sensible default set)
    # Dynamic from trader basket config (full opportunity pool)
    try:
        cfg = json.load(open("../../../config/trading_config_phase6.json"))
        pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool") or cfg.get("global_settings", {}).get("pairs", ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"])
    except:
        pairs = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD", "MATIC-USD"]

    keywords_dict = {pair: pair.split('-')[0] for pair in pairs}

    bearer_token = load_bearer_token()
    if not bearer_token:
        print("❌ ERROR: No X Bearer Token — writing neutral cache")
        cache = {pair: {"sentiment": 0.0, "timestamp": datetime.utcnow().isoformat()} for pair in pairs}
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
        return

    print(f"🔍 Fetching X sentiment for {len(pairs)} pairs (combined query)...")

    keywords = [pair.split('-')[0] for pair in pairs]
    posts = fetch_x_posts_for_sentiment_analysis(
        bearer_token=bearer_token,
        keywords=keywords,
        max_results=100,
        language="en"
    )
    print(f"  Got {len(posts)} total posts from X API")

    pair_posts = distribute_posts_to_pairs(posts, keywords_dict)

    all_sentiments = {}
    for pair in pairs:
        posts_for_pair = pair_posts[pair]
        sentiment = calculate_sentiment(posts_for_pair)
        all_sentiments[pair] = sentiment
        print(f"  {pair}: {sentiment:.6f} ({len(posts_for_pair)} posts)")

    timestamp = datetime.utcnow().isoformat()
    cache = {
        pair: {
            "sentiment": all_sentiments.get(pair, 0.0),
            "timestamp": timestamp,
            "post_count": len(pair_posts.get(pair, []))
        }
        for pair in pairs
    }

    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"✅ X sentiment cached to {CACHE_FILE}")
    print(json.dumps(all_sentiments, indent=2))


# Apify fallback (kept for robustness)
def fetch_x_sentiment_apify(query: str = "bitcoin OR ethereum OR solana OR dogecoin OR xrp", max_items: int = 50) -> Dict[str, float]:
    """Apify Twitter Search Scraper fallback."""
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
    run_input = {"searchTerms": [query], "maxItems": max_items, "sort": "Latest"}

    try:
        run = client.actor("apify/twitter-search-scraper").call(run_input=run_input)
        dataset = client.dataset(run["defaultDatasetId"])
        items = list(dataset.iterate_items())

        positive_words = {"bullish", "moon", "buy", "up", "good", "great", "pump"}
        negative_words = {"bearish", "dump", "sell", "down", "bad", "crash", "scam"}

        scores = {}
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


if __name__ == "__main__":
    main()
