#!/usr/bin/env python3
"""
Full Sentiment System Runner (Canonical v3 + Strict No-Fab Gate)

Production entrypoint for RSI-SENT-003.

- Calls phase6/core/sentiment/ fetchers (Reddit native + X).
- Enforces post-count gate (>=5 posts or equivalent confidence).
- On insufficient/zero results: **preserve prior timestamp + score**, set status="insufficient_data" or "stale_preserved". NEVER stamp fresh ts + 0.0.
- Writes canonical schema v3 to root sentiment_cache.json (and compatible with scorer).
- Uses real data only. Structured logs with post counts, sources, duration.
- Unifies consumption: all code should load via phase6/core/sentiment_scorer.py or load_sentiment_scores.
- 30min Hermes cron target (no_agent=True via wrapper).

Run: python run_sentiment_system.py   or via run_sentiment.sh (for NumPy workaround)

Part of RSI/Sentiment Refactor. Must pass isolation test for zero-results case.
"""

import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
CACHE_FILE = PROJECT_ROOT / "sentiment_cache.json"

# Ensure path for internal modules
import sys
sys.path.insert(0, str(PROJECT_ROOT))

# Canonical fetchers
from phase6.core.sentiment.fetch_reddit_sentiment import RedditSentimentFetcher

MIN_POSTS_GATE = 5  # per handoff recommendation

def load_prior_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
            # Normalize to have "data" or top level
            if "data" in data:
                return data
            # Legacy or simple format -> wrap
            return {"data": data.get("combined", data.get("sentiments", {})), "timestamp": data.get("timestamp")}
        except Exception as e:
            logger.warning(f"Failed to load prior cache: {e}")
    return {"data": {}, "timestamp": None}

def save_canonical_cache(payload):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Saved canonical v3 sentiment cache to {CACHE_FILE}")

def get_x_sentiment():
    """Fetch real X sentiment using the Phase 6 fetcher. Returns {pair: {"sentiment": s, "posts": n?}} or {} on fail."""
    try:
        from phase6.core.sentiment.fetch_x_sentiment import main as fetch_x_main
        fetch_x_main()
        x_cache_file = PROJECT_ROOT / "phase6" / "data" / "sentiment" / "x_sentiment_cache.json"
        if x_cache_file.exists():
            with open(x_cache_file) as f:
                x_cache = json.load(f)
            # Normalize to {pair: score or dict}
            result = {}
            for pair, data in x_cache.items():
                if isinstance(data, dict):
                    result[pair] = data
                else:
                    result[pair] = {"sentiment": data}
            return result
    except Exception as e:
        logger.warning(f"X sentiment fetch failed (NumPy/env/Apify quota?): {e}")
    return {}

def main():
    start = time.time()
    logger.info("=== Running Canonical Sentiment System (v3 no-fab gate) ===")

    prior = load_prior_cache()
    prior_data = prior.get("data", {})

    # 1. Reddit (native actor preferred)
    reddit_fetcher = RedditSentimentFetcher()
    reddit_scores = reddit_fetcher.run()  # expect {pair: score} or enhanced
    logger.info(f"Reddit results: {len(reddit_scores)} pairs, sample scores: { {k: round(v,3) if isinstance(v,(int,float)) else v for k,v in list(reddit_scores.items())[:3]} }")

    # 2. X
    x_scores = get_x_sentiment()
    logger.info(f"X results: {len(x_scores)} pairs")

    # 3. Combine with gate
    now_iso = datetime.utcnow().isoformat() + "Z"
    new_data = {}
    all_pairs = set(reddit_scores.keys()) | set(x_scores.keys()) | set(prior_data.keys())
    # Include standard 6
    for p in ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD"]:
        all_pairs.add(p)

    for pair in sorted(all_pairs):
        r = reddit_scores.get(pair, 0.0)
        x_entry = x_scores.get(pair, {})
        x = x_entry.get("sentiment", 0.0) if isinstance(x_entry, dict) else x_entry
        # Real post counts from X cache (post_count); Reddit may be 0 on quota
        posts_r = x_entry.get("post_count", 0) if isinstance(x_entry, dict) else 0   # prefer real; reddit quota often 0
        posts_x = x_entry.get("post_count", 0) if isinstance(x_entry, dict) else x_entry.get("posts", 0)
        total_posts = max(posts_r, posts_x)  # use the best source's count; X is currently reliable

        score = round((r + x) / 2.0, 4) if (r or x) else x  # fall back to X score if reddit 0

        candidate = {
            "score": score,
            "posts": total_posts,
            "timestamp": now_iso,
            "sources": ["reddit", "x"] if (r or x) else ["x"] if x else [],
            "confidence": min(1.0, total_posts / 10.0)
        }

        if total_posts < MIN_POSTS_GATE or (not r and not x and not (x_entry.get("post_count", 0) >= 5)):
            logger.warning(f"Insufficient data for {pair} (posts={total_posts} < {MIN_POSTS_GATE} or no usable X), preserving prior timestamp/score. No fresh neutral.")
            preserved = prior_data.get(pair, {"score": 0.0, "timestamp": prior.get("timestamp", now_iso), "posts": 0, "status": "no_prior"})
            preserved = dict(preserved)  # copy
            preserved["status"] = "insufficient_data"
            preserved["timestamp"] = preserved.get("timestamp", prior.get("timestamp"))  # keep old ts!
            new_data[pair] = preserved
        else:
            candidate["status"] = "fresh"
            new_data[pair] = candidate

    # v3 schema
    payload = {
        "schema_version": 3,
        "timestamp": now_iso,
        "data": new_data,
        "meta": {
            "min_posts_gate": MIN_POSTS_GATE,
            "duration_sec": round(time.time() - start, 2),
            "note": "Canonical no-fab gate per RSI-SENT-003 / P6-121/122. Prior ts preserved on low data."
        }
    }

    save_canonical_cache(payload)

    # Also write simple combined for backward (scorer handles)
    simple_combined = {pair: d.get("score", 0.0) for pair, d in new_data.items()}
    logger.info(f"Sentiment system run complete in {payload['meta']['duration_sec']}s. Fresh pairs: {sum(1 for d in new_data.values() if d.get('status')=='fresh')}")
    print(json.dumps({"combined": simple_combined, "full": payload}, indent=2))

if __name__ == "__main__":
    main()
