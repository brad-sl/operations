#!/usr/bin/env python3
"""
Phase 6 - Sentiment Refresh Orchestrator (runs every 30 minutes)
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

PHASE6_ROOT = Path("/home/brad/projects/crypto-trading-bot/phase6")
sys.path.insert(0, str(PHASE6_ROOT))

# Import the actual main functions from the fetchers
from phase6.core.sentiment.fetch_x_sentiment import main as fetch_x_main
from phase6.core.sentiment.fetch_reddit_sentiment import main as fetch_reddit_main

UNIFIED_CACHE = PHASE6_ROOT / "data" / "sentiment" / "unified_sentiment_cache.json"
UNIFIED_CACHE.parent.mkdir(parents=True, exist_ok=True)

def main():
    print(f"=== Sentiment Refresh @ {datetime.now(timezone.utc).isoformat()} ===")
    
    # Run the existing fetchers (they write their own caches)
    try:
        fetch_x_main()
        print("  X fetch completed")
    except Exception as e:
        print(f"  X fetch error: {e}")

    try:
        fetch_reddit_main()
        print("  Reddit fetch completed")
    except Exception as e:
        print(f"  Reddit fetch error: {e}")

    # Merge X + Reddit caches into unified format
    try:
        x_cache = PHASE6_ROOT / "data" / "sentiment" / "x_sentiment_cache.json"
        reddit_cache = PHASE6_ROOT / "data" / "sentiment" / "reddit_sentiment_cache.json"

        unified = {"sentiment": {}, "last_updated": datetime.now(timezone.utc).isoformat()}

        # Load X sentiment
        if x_cache.exists():
            with open(x_cache) as f:
                x_data = json.load(f)
            for pair, entry in x_data.items():
                if isinstance(entry, dict):
                    unified["sentiment"][pair] = {
                        "sentiment_score": entry.get("sentiment_score", 0.0),
                        "source": "x"
                    }

        # Load Reddit sentiment (merge/override)
        if reddit_cache.exists():
            with open(reddit_cache) as f:
                reddit_data = json.load(f)
            for pair, entry in reddit_data.items():
                if isinstance(entry, dict):
                    if pair not in unified["sentiment"]:
                        unified["sentiment"][pair] = {"source": "reddit"}
                    unified["sentiment"][pair]["sentiment_score"] = entry.get("sentiment_score", 0.0)
                    unified["sentiment"][pair]["source"] = "reddit" if pair not in unified["sentiment"] else "merged"

        # Write unified cache
        with open(UNIFIED_CACHE, "w") as f:
            json.dump(unified, f, indent=2)

        print(f"  Unified cache written with {len(unified['sentiment'])} pairs")
    except Exception as e:
        print(f"  Failed to build unified cache: {e}")

    print("=== Refresh complete ===")

if __name__ == "__main__":
    main()
