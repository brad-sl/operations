#!/usr/bin/env python3
"""Capture before/after sentiment cache state for comparison."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Actual paths used by the fetch scripts
X_CACHE_PATH = Path("phase6/data/sentiment/x_sentiment_cache.json")
REDDIT_CACHE_PATH = Path("reddit_sentiment_cache.json")

def load_cache(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def capture(label: str):
    print(f"=== {label.upper()} STATE CAPTURE ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    x_cache = load_cache(X_CACHE_PATH)
    reddit_cache = load_cache(REDDIT_CACHE_PATH)

    print("\nX cache (from phase6/data/sentiment/):")
    if x_cache:
        for pair in sorted(x_cache.keys()):
            d = x_cache[pair]
            sent = d.get('sentiment', 0)
            posts = d.get('post_count', 0)
            conf = d.get('confidence', 0)
            print(f"  {pair}: sent={sent:+.4f}, posts={posts:3d}, conf={conf:.2f}")
    else:
        print("  (empty or not found)")

    print("\nReddit cache (root):")
    nonzero = 0
    if reddit_cache:
        for pair in sorted(reddit_cache.keys()):
            d = reddit_cache[pair]
            sent = d.get('sentiment', 0)
            posts = d.get('post_count', 0)
            if sent != 0:
                nonzero += 1
            print(f"  {pair}: sent={sent:+.4f}, posts={posts:3d}")
        print(f"\nNon-zero Reddit: {nonzero}/11")
    else:
        print("  (empty)")

    snapshot = {
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "x_cache": x_cache,
        "reddit_cache": reddit_cache,
    }
    Path("data/state").mkdir(parents=True, exist_ok=True)
    out = f"data/state/sentiment_{label.lower()}_state.json"
    with open(out, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"\nSaved: {out}")
    return snapshot

if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "manual"
    capture(label)