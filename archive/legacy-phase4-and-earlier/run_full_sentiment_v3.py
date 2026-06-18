#!/usr/bin/env python3
"""
Canonical Sentiment Collector (v3 - actor native)

Single source of truth for sentiment data.

- Uses Apify Reddit actor with native sentiment_analysis=True for reliability and simplicity.
- Minimal local scoring logic (trust the actor's normalized scores).
- Writes to the single canonical cache: sentiment_cache.json (root of project).
- Format is simple, self-describing, and consumable by trading logic, reports, and dashboards.
- Real data only. No fakes, no complex TextBlob/keyword hybrids.

This replaces all previous duplicate fetchers (fetch_reddit, fetch_x, run_sentiment_system, etc.).

Run via: scripts/run_sentiment.sh or directly.
"""

import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()
client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

ACTOR_ID = "TwqHBuZZPHJxiQrTU"  # Reddit scraper with built-in sentiment

# Dynamic basket from config (supports per-trader baskets via config or future DB trader_baskets)
# Load the full opportunity pool / trading basket so runner/rebalancer can promote/liquidate dynamically.
try:
    cfg = json.load(open("config/trading_config_phase6.json"))
    opp = cfg.get("phase_6_specific", {}).get("opportunity_pool") or cfg.get("global_settings", {}).get("pairs", [])
    # Map to keywords for Apify (simple for now; can be enhanced)
    KEYWORD_MAP = {
        "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
        "XRP-USD": "ripple", "DOGE-USD": "dogecoin", "ADA-USD": "cardano",
        "AVAX-USD": "avalanche", "LINK-USD": "chainlink", "UNI-USD": "uniswap",
        "ARB-USD": "arbitrum", "OP-USD": "optimism", "MATIC-USD": "polygon"
    }
    PAIRS = {p: KEYWORD_MAP.get(p, p.lower().replace("-USD","")) for p in opp if p in KEYWORD_MAP or True}
except Exception:
    PAIRS = {
        'BTC-USD': 'bitcoin', 'ETH-USD': 'ethereum', 'SOL-USD': 'solana',
        'XRP-USD': 'ripple', 'DOGE-USD': 'dogecoin', 'ADA-USD': 'cardano',
        'AVAX-USD': 'avalanche', 'LINK-USD': 'chainlink', 'UNI-USD': 'uniswap',
        'ARB-USD': 'arbitrum', 'OP-USD': 'optimism'
    }


CANONICAL_CACHE = "/home/brad/projects/crypto-trading-bot/sentiment_cache.json"


def fetch_sentiment(keyword, max_posts=25):
    """Call the Apify actor for one coin. Returns list of result items with native scores."""
    run_input = {
        "queries": [keyword],
        "subredditName": "CryptoCurrency",
        "sort": "relevance",
        "timeframe": "week",
        "scrapeComments": True,
        "maxComments": 20,
        "includeNsfw": False,
        "strictSearch": False,
        "maxPosts": max_posts,
        "sentiment_analysis": True,
        "content_analysis": False,
    }
    run = client.actor(ACTOR_ID).call(run_input=run_input)
    dataset = client.dataset(run["defaultDatasetId"])
    # properly iterate dataset items
    return list(dataset.iterate_items())


def extract_score(item):
    """Prefer native normalized sentiment_score from the actor. Simple fallbacks only."""
    if not isinstance(item, dict):
        return 0.0

    if "sentiment_score_normalized" in item:
        return float(item["sentiment_score_normalized"])
    if "sentiment_score" in item:
        return float(item["sentiment_score"])

    # Minimal fallback only if actor didn't provide score
    label = str(item.get("sentiment_label", "")).lower()
    if label == "positive":
        return 0.6
    elif label == "negative":
        return -0.6
    elif label in ("mixed", "neutral"):
        return 0.0

    # Last resort keyword (rarely hit)
    text = str(item.get("body") or item.get("title", "")).lower()
    bull = sum(1 for w in ["moon", "pump", "bull", "buy", "gain", "hodl"] if w in text)
    bear = sum(1 for w in ["crash", "dump", "bear", "scam", "loss"] if w in text)
    if bull + bear > 0:
        return (bull - bear) / (bull + bear)
    return 0.0


def aggregate_sentiment(items):
    """Simple average of per-post scores. Returns (score, count)."""
    if not items:
        return 0.0, 0
    scores = [extract_score(i) for i in items]
    valid_scores = [s for s in scores if s != 0.0] or scores  # include zeros
    avg = sum(scores) / len(scores) if scores else 0.0
    return round(avg, 4), len(items)


def write_canonical_cache(results):
    """Write the single source-of-truth cache in a clean, future-proof format."""
    cache = {
        "schema_version": 3,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": f"run_full_sentiment_v3.py + Apify actor {ACTOR_ID} (native sentiment)",
        "sentiment": {},
        "meta": {
            "actor": ACTOR_ID,
            "posts_analyzed": {},
            "note": "Single canonical sentiment cache. All trading, reporting, and dashboards should read from here."
        }
    }

    # Load existing cache to preserve old values if new run is deficient
    try:
        with open(CANONICAL_CACHE, "r") as f:
            old_cache = json.load(f)
            old_sentiments = old_cache.get("sentiment", {})
            old_posts = old_cache.get("meta", {}).get("posts_analyzed", {})
            old_ts = old_cache.get("sentiment_timestamps", {})
    except (FileNotFoundError, json.JSONDecodeError):
        old_sentiments = {}
        old_posts = {}
        old_ts = {}

    cache["sentiment_timestamps"] = old_ts

    for pair, data in results.items():
        if data["sentiment"] is not None:
            cache["sentiment"][pair] = round(data["sentiment"], 4)
            cache["meta"]["posts_analyzed"][pair] = data["posts"]
            cache["sentiment_timestamps"][pair] = data["timestamp"]
        else:
            # Preservation
            cache["sentiment"][pair] = old_sentiments.get(pair, 0.0)
            cache["meta"]["posts_analyzed"][pair] = old_posts.get(pair, 0)
            # keep old timestamp

    with open(CANONICAL_CACHE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"\n✅ Canonical sentiment cache written to {CANONICAL_CACHE}")
    print(json.dumps(cache, indent=2))

    # Dual-write to phase6.db sentiment_scores table (aligns RSI/Sentiment refresh output with DASH-SQL shared schema)
    try:
        import sqlite3
        from pathlib import Path
        dbp = Path("/home/brad/projects/crypto-trading-bot/data/phase6.db")
        conn = sqlite3.connect(str(dbp))
        cur = conn.cursor()
        now_ts = datetime.now(timezone.utc).isoformat()
        for pair, val in cache.get("sentiment", {}).items():
            sc = float(val) if val is not None else 0.0
            posts = cache.get("meta", {}).get("posts_analyzed", {}).get(pair, 0)
            cur.execute(
                "INSERT OR REPLACE INTO sentiment_scores (ts, pair, score, posts, source) VALUES (?, ?, ?, ?, ?)",
                (now_ts, pair, sc, posts, "run_full_sentiment_v3")
            )
        conn.commit()
        conn.close()
        print(f"  Dual-written {len(cache.get('sentiment', {}))} sentiment rows to phase6.db")
    except Exception as e:
        print(f"  WARN: sentiment DB dual-write failed: {e}")

    return cache


def main():
    print("=== Canonical Sentiment Collection (v3 - single source) ===\n")

    post_count_threshold = 5

    results = {}
    for pair, kw in PAIRS.items():
        try:
            items = fetch_sentiment(kw)
            if not items or len(items) < post_count_threshold:
                print(f"{pair}: WARNING - Insufficient data ({len(items)} posts < {post_count_threshold}). Marking error/preservation.")
                results[pair] = {"sentiment": None, "posts": len(items), "timestamp": None}
            else:
                score, count = aggregate_sentiment(items)
                results[pair] = {
                    "sentiment": score,
                    "posts": count,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                print(f"{pair}: {score:+.4f} ({count} posts analyzed)")
        except Exception as e:
            print(f"{pair}: ERROR - {e}. Marking error/preservation.")
            results[pair] = {"sentiment": None, "posts": 0, "timestamp": None}

    write_canonical_cache(results)
    print("\n=== Sentiment collection complete (single cache updated) ===")


if __name__ == "__main__":
    main()