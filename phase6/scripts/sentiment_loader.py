#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py for paths, state, config hygiene
"""
sentiment_loader.py — Production sentiment integration for Phase 6

Loads live sentiment scores from the sentiment pipeline cache.
Handles both flat and nested cache formats. Real data only.
"""

import json
import logging
from pathlib import Path
from typing import Tuple, Dict, List

logger = logging.getLogger("sentiment-loader")

CACHE_PATH = Path.home() / ".trading-bot" / "sentiment_cache.json"
DEFAULT_CANDIDATES = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "ADA-USD", "DOGE-USD"]


def load_live_sentiment() -> Tuple[Dict[str, float], List[str]]:
    """
    Load real sentiment scores from the shared cache.
    Supports both flat {pair: score} and nested {"sentiment": {pair: {"sentiment_score": ...}}}
    """
    if not CACHE_PATH.exists():
        logger.warning(f"Sentiment cache not found at {CACHE_PATH}")
        return {}, DEFAULT_CANDIDATES

    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)

        sentiment = {}

        # Case 1: Nested format from pipeline
        if "sentiment" in data and isinstance(data["sentiment"], dict):
            for pair, info in data["sentiment"].items():
                if isinstance(info, dict) and "sentiment_score" in info:
                    sentiment[pair] = float(info["sentiment_score"])
                elif isinstance(info, (int, float)):
                    sentiment[pair] = float(info)

        # Case 2: Flat format
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (int, float)):
                    sentiment[k] = float(v)

        if sentiment:
            candidates = list(sentiment.keys())
            logger.info(f"Loaded {len(sentiment)} real sentiment scores from cache")
            return sentiment, candidates
        else:
            logger.warning("Sentiment cache has no usable scores")
            return {}, DEFAULT_CANDIDATES

    except Exception as e:
        logger.error(f"Failed to load sentiment cache: {e}")
        return {}, DEFAULT_CANDIDATES


if __name__ == "__main__":
    sentiment, candidates = load_live_sentiment()
    print(f"Sentiment: {sentiment}")
    print(f"Candidates: {candidates}")