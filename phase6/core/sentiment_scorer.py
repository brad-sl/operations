#!/usr/bin/env python3
"""
Basic Sentiment Scorer Module

Loads sentiment scores from ~/.trading-bot/sentiment_cache.json
and provides scores for the fixed trading universe.
"""

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = os.path.expanduser("~/.trading-bot/sentiment_cache.json")


def load_sentiment_scores(
    cache_path: str = DEFAULT_CACHE_PATH,
    universe: List[str] = None
) -> Dict[str, float]:
    """
    Load sentiment scores from cache JSON.

    Returns dict of symbol -> sentiment_score (float, typically -1.0 to 1.0)
    Falls back to 0.0 for missing symbols or load errors.
    """
    if universe is None:
        universe = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]

    scores: Dict[str, float] = {sym: 0.0 for sym in universe}

    try:
        if not os.path.exists(cache_path):
            logger.warning(f"Sentiment cache not found at {cache_path}, using neutral scores")
            return scores

        with open(cache_path, "r") as f:
            data = json.load(f)

        sentiment_data = data.get("sentiment", {})
        for sym in universe:
            if sym in sentiment_data:
                entry = sentiment_data[sym]
                score = entry.get("sentiment_score", 0.0)
                try:
                    scores[sym] = float(score)
                except (ValueError, TypeError):
                    scores[sym] = 0.0
                logger.debug(f"Loaded sentiment for {sym}: {scores[sym]}")
            else:
                logger.debug(f"No sentiment entry for {sym}, defaulting to 0.0")

    except Exception as e:
        logger.warning(f"Failed to load sentiment cache: {e}. Using neutral scores.")
        scores = {sym: 0.0 for sym in universe}

    return scores


def get_sentiment_adjusted_weights(
    base_weights: Dict[str, float],
    sentiment_scores: Dict[str, float],
    sentiment_weight: float = 0.2
) -> Dict[str, float]:
    """
    Simple integration: boost weights for positive sentiment, reduce for negative.
    Keeps weights summing to 1.0.
    """
    if not base_weights:
        return {}

    adjusted = {}
    total = 0.0
    for sym, base_w in base_weights.items():
        sent = sentiment_scores.get(sym, 0.0)
        # Simple linear adjustment: positive sent increases weight
        adj = base_w * (1.0 + sentiment_weight * sent)
        adjusted[sym] = max(0.01, adj)  # floor to avoid zero
        total += adjusted[sym]

    # Renormalize
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted
