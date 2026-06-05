#!/usr/bin/env python3
"""
Basic Sentiment Scorer Module

Loads sentiment scores from /home/brad/projects/crypto-trading-bot/phase6/data/sentiment/unified_sentiment_cache.json
and provides scores for the fixed trading universe.
"""

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = os.path.expanduser("/home/brad/projects/crypto-trading-bot/phase6/data/sentiment/unified_sentiment_cache.json")


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


# ============================================================
# Report Formatting Helpers (for Trading Intelligence Report)
# ============================================================

def format_rsi_label(rsi: float) -> str:
    """Return human-readable label for RSI value."""
    if rsi < 30:
        return "Oversold"
    elif rsi < 45:
        return "Weak"
    elif rsi < 55:
        return "Neutral"
    elif rsi < 70:
        return "Strong"
    else:
        return "Overbought"


def format_sentiment_label(score: float) -> str:
    """Return human-readable label + emoji for sentiment score."""
    if score > 0.3:
        return "Bullish"
    elif score > 0.1:
        return "Slightly Bullish"
    elif score > -0.1:
        return "Neutral"
    elif score > -0.3:
        return "Slightly Bearish"
    else:
        return "Bearish"


def format_sentiment_for_report(scores: dict) -> str:
    """Format sentiment dict for the intelligence report."""
    lines = []
    for pair, score in scores.items():
        label = format_sentiment_label(score)
        lines.append(f"{pair.replace('-USD','')}: {score:+.2f} ({label})")
    return " | ".join(lines)


def format_rsi_for_report(rsi_values: dict) -> str:
    """Format RSI dict for the intelligence report with labels."""
    lines = []
    for pair, rsi in rsi_values.items():
        label = format_rsi_label(rsi)
        lines.append(f"{pair.replace('-USD','')}: {rsi:.1f} ({label})")
    return " | ".join(lines)
