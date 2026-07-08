#!/usr/bin/env python3
"""
Phase 6 Sentiment Scorer with Time Decay

Combines X (15-min half-life) and Reddit (60-min half-life) sentiment.
Applies exponential time decay so stale data loses influence.

This is the unified signal path that was missing in the initial Phase 6 port.

See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py (prefer main core/sentiment_scorer.py for canonical).
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from ..paths import X_SENTIMENT_CACHE, REDDIT_SENTIMENT_CACHE, load_trading_basket  # per DATA_FLOW_AND_LOCATIONS.md ; note relative from subdir

X_CACHE = X_SENTIMENT_CACHE
REDDIT_CACHE = REDDIT_SENTIMENT_CACHE

# Staleness thresholds (Grok Build review intent: zero instead of decayed old values)
X_STALENESS_THRESHOLD_MIN = 120      # 2h for X
REDDIT_STALENESS_THRESHOLD_MIN = 240  # 4h for Reddit


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse various timestamp formats to UTC datetime."""
    if not ts:
        return None
    ts = ts.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None


def _exponential_decay(last_ts: str, half_life_minutes: float, staleness_threshold_min: Optional[float] = None) -> float:
    """
    Calculate decay factor (0.0 - 1.0) using exponential half-life.
    If age > staleness_threshold_min, return 0.0 (neutral/zero per review intent).
    half_life_minutes: 15 for X, 60 for Reddit.
    """
    ts = _parse_timestamp(last_ts)
    if not ts:
        return 0.0

    age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
    if age_minutes <= 0:
        return 1.0

    if staleness_threshold_min is not None and age_minutes > staleness_threshold_min:
        return 0.0

    # decay = 0.5 ^ (age / half_life)
    decay = math.pow(0.5, age_minutes / half_life_minutes)
    return max(0.0, min(1.0, decay))


def load_sentiment_scores(pairs: Optional[list] = None) -> Dict[str, Dict[str, Any]]:
    """
    Load and merge X + Reddit sentiment with proper time decay.

    Returns dict like:
    {
        "BTC-USD": {
            "combined": 0.42,
            "x": {"raw": 0.55, "decayed": 0.48, "age_min": 12},
            "reddit": {"raw": 0.31, "decayed": 0.29, "age_min": 47},
            "timestamp": "..."
        }
    }
    """
    if pairs is None:
        pairs = load_trading_basket()

    x_data = {}
    reddit_data = {}

    # Load X cache
    if X_CACHE.exists():
        try:
            with open(X_CACHE) as f:
                x_data = json.load(f)
        except Exception:
            pass

    # Load Reddit cache
    if REDDIT_CACHE.exists():
        try:
            with open(REDDIT_CACHE) as f:
                reddit_data = json.load(f)
        except Exception:
            pass

    result = {}
    for pair in pairs:
        x_entry = x_data.get(pair, {})
        reddit_entry = reddit_data.get(pair, {})

        x_raw = x_entry.get("sentiment", 0.0) if isinstance(x_entry, dict) else 0.0
        reddit_raw = reddit_entry.get("sentiment", 0.0) if isinstance(reddit_entry, dict) else 0.0

        x_ts = x_entry.get("timestamp", "") if isinstance(x_entry, dict) else ""
        reddit_ts = reddit_entry.get("timestamp", "") if isinstance(reddit_entry, dict) else ""

        x_decay = _exponential_decay(x_ts, 15, X_STALENESS_THRESHOLD_MIN)      # 15 min half-life, 2h staleness
        reddit_decay = _exponential_decay(reddit_ts, 60, REDDIT_STALENESS_THRESHOLD_MIN)  # 60 min half-life, 4h staleness

        x_decayed = x_raw * x_decay
        reddit_decayed = reddit_raw * reddit_decay

        # Weighted combination (X slightly higher weight because faster signal)
        combined = (0.6 * x_decayed) + (0.4 * reddit_decayed)

        result[pair] = {
            "combined": round(combined, 4),
            "x": {
                "raw": round(x_raw, 4),
                "decayed": round(x_decayed, 4),
                "decay_factor": round(x_decay, 3),
                "age_min": round((datetime.now(timezone.utc) - (_parse_timestamp(x_ts) or datetime.now(timezone.utc))).total_seconds() / 60, 1)
            },
            "reddit": {
                "raw": round(reddit_raw, 4),
                "decayed": round(reddit_decayed, 4),
                "decay_factor": round(reddit_decay, 3),
                "age_min": round((datetime.now(timezone.utc) - (_parse_timestamp(reddit_ts) or datetime.now(timezone.utc))).total_seconds() / 60, 1)
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    return result


def get_sentiment_adjusted_weights(base_weights: Dict[str, float], sentiment_scores: Optional[Dict] = None) -> Dict[str, float]:
    """
    Apply sentiment to base allocation weights.
    Positive sentiment increases weight.
    """
    if sentiment_scores is None:
        sentiment_scores = load_sentiment_scores(list(base_weights.keys()))

    adjusted = {}
    total = 0.0
    for pair, base_w in base_weights.items():
        sent = sentiment_scores.get(pair, {}).get("combined", 0.0)
        adj = base_w * (1.0 + 0.25 * sent)   # 25% sentiment influence
        adjusted[pair] = max(0.01, adj)
        total += adjusted[pair]

    if total > 0:
        adjusted = {k: round(v / total, 6) for k, v in adjusted.items()}
    return adjusted


if __name__ == "__main__":
    scores = load_sentiment_scores()
    print(json.dumps(scores, indent=2))