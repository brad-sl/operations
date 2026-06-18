#!/usr/bin/env python3
"""
Phase 6 - Sentiment Refresh Orchestrator (runs every 30 minutes)

Properly structured version:
- Calls the stable root-level fetch scripts via subprocess
- Merges results into the canonical cache used by scripts/sentiment_scorer.py
- Writes to ~/.trading-bot/sentiment_cache.json (the location the runner expects)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/home/brad/projects/crypto-trading-bot")
CANONICAL_CACHE = Path.home() / ".trading-bot" / "sentiment_cache.json"
CANONICAL_CACHE.parent.mkdir(parents=True, exist_ok=True)

X_FETCH = PROJECT_ROOT / "fetch_x_sentiment.py"
REDDIT_FETCH = PROJECT_ROOT / "fetch_reddit_sentiment.py"

X_CACHE = PROJECT_ROOT / "sentiment_cache.json"
REDDIT_CACHE = PROJECT_ROOT / "reddit_sentiment_cache.json"


def run_fetcher(script_path: Path, name: str) -> bool:
    """Run a fetch script and return success status."""
    print(f"  Running {name}...")
    try:
        # Use the canonical wrapper to apply NumPy workarounds
        env = os.environ.copy()
        env["OPENBLAS_CORETYPE"] = "GENERIC"
        cmd = ["/home/brad/projects/crypto-trading-bot/run_sentiment.sh", str(script_path)]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode == 0:
            print(f"    {name} completed successfully")
            return True
        else:
            print(f"    {name} failed (exit {result.returncode})")
            if result.stderr:
                print(f"    stderr: {result.stderr.strip()[:300]}")
            return False
    except Exception as e:
        print(f"    {name} exception: {e}")
        return False


def merge_into_canonical():
    """Merge X + Reddit caches into the format expected by sentiment_scorer.py."""
    unified = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sentiment": {},
        "meta": {
            "source": "refresh_sentiment.py",
            "x_cache": str(X_CACHE),
            "reddit_cache": str(REDDIT_CACHE)
        }
    }

    # Load X sentiment (root sentiment_cache.json format)
    if X_CACHE.exists():
        try:
            with open(X_CACHE) as f:
                x_data = json.load(f)
            # The X fetcher writes {"sentiments": {...}} or direct pair dict
            sentiments = x_data.get("sentiments", x_data)
            for pair, entry in sentiments.items():
                if isinstance(entry, dict):
                    score = entry.get("sentiment_score", entry.get("score", 0.0))
                else:
                    score = float(entry) if entry else 0.0
                unified["sentiment"][pair] = {
                    "sentiment_score": float(score),
                    "source": "x"
                }
        except Exception as e:
            print(f"  Warning: failed to read X cache: {e}")

    # Load Reddit sentiment (merges/overrides)
    if REDDIT_CACHE.exists():
        try:
            with open(REDDIT_CACHE) as f:
                reddit_data = json.load(f)
            sentiments = reddit_data.get("sentiments", reddit_data)
            for pair, entry in sentiments.items():
                if isinstance(entry, dict):
                    score = entry.get("sentiment_score", entry.get("score", 0.0))
                else:
                    score = float(entry) if entry else 0.0
                if pair not in unified["sentiment"]:
                    unified["sentiment"][pair] = {"source": "reddit"}
                unified["sentiment"][pair]["sentiment_score"] = float(score)
                if "source" in unified["sentiment"][pair]:
                    unified["sentiment"][pair]["source"] = "merged"
        except Exception as e:
            print(f"  Warning: failed to read Reddit cache: {e}")

    # Write canonical cache
    with open(CANONICAL_CACHE, "w") as f:
        json.dump(unified, f, indent=2)

    print(f"  Canonical cache updated: {CANONICAL_CACHE} ({len(unified['sentiment'])} pairs)")


def main():
    print(f"=== Sentiment Refresh @ {datetime.now(timezone.utc).isoformat()} ===")

    x_ok = run_fetcher(X_FETCH, "X/Twitter sentiment")
    reddit_ok = run_fetcher(REDDIT_FETCH, "Reddit sentiment")

    if x_ok or reddit_ok:
        try:
            merge_into_canonical()
        except Exception as e:
            print(f"  Merge failed: {e}")
    else:
        print("  No fetchers succeeded — skipping merge")

    print("=== Refresh complete ===")


if __name__ == "__main__":
    main()