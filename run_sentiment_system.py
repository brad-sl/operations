#!/usr/bin/env python3
"""
Full Sentiment System Runner (X + Reddit)
Production version with fallback scoring.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

CACHE_FILE = Path("/home/brad/projects/crypto-trading-bot/sentiment_cache.json")

# Import local modules
import sys
sys.path.insert(0, str(Path(__file__).parent / "phase6/core/sentiment"))

from fetch_reddit_sentiment import RedditSentimentFetcher

def load_rsi_from_live_state():
    """Load latest RSI values from the Phase 6 runner cache."""
    try:
        state_file = Path("/home/brad/projects/crypto-trading-bot/data/state/phase6_live_state.json")
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
                return state.get("rsi", {})
    except Exception as e:
        logger.warning(f"Could not load RSI from live state: {e}")
    return {}


def get_x_sentiment():
    """Placeholder - X credentials need path fix in fetch_x_sentiment.py"""
    logger.warning("X sentiment temporarily disabled (credential path issue)")
    return {pair: 0.0 for pair in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD', 'ADA-USD']}


def main():
    logger.info("=== Running Full Sentiment System ===")

    # Reddit
    reddit_fetcher = RedditSentimentFetcher()
    reddit_scores = reddit_fetcher.run()

    # X (placeholder for now)
    x_scores = get_x_sentiment()

    # RSI from Phase 6 runner
    rsi_scores = load_rsi_from_live_state()
    if rsi_scores:
        logger.info(f"RSI values loaded: {rsi_scores}")

    # Combine (simple average for now)
    combined = {}
    all_pairs = set(reddit_scores.keys()) | set(x_scores.keys())

    for pair in all_pairs:
        r = reddit_scores.get(pair, 0.0)
        x = x_scores.get(pair, 0.0)
        combined[pair] = round((r + x) / 2, 4)

    # Save
    cache = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reddit": reddit_scores,
        "x": x_scores,
        "combined": combined
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    logger.info("Sentiment system run complete")
    print(json.dumps(cache, indent=2))


if __name__ == "__main__":
    main()