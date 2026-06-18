#!/usr/bin/env python3
"""
Canonical Sentiment Scorer / Loader (single source of truth)

All trading logic, reports, and dashboards MUST use this module
to retrieve current sentiment scores.

- Reads exclusively from the canonical cache: sentiment_cache.json (project root)
- Written by the canonical fetcher: run_full_sentiment_v3.py
- Simple, reliable, no duplicate logic or caches.
- Always returns scores for the requested universe (defaults to core 5 pairs).
- Includes timestamp for freshness checks.
- Applies appropriate sentiment aging (exponential decay, half-life 60min default) for conservative use of stale data.
- Real data only.

Consumers:
- phase6 runner, backtests, deploy logic, paper harness
- intelligence reports
- live dashboards (serve_live_8501)
- any future loops or signal generators
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CANONICAL_CACHE = "/home/brad/projects/crypto-trading-bot/sentiment_cache.json"
X_CACHE = "/home/brad/projects/crypto-trading-bot/phase6/data/sentiment/x_sentiment_cache.json"

DEFAULT_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD", "MATIC-USD"
]  # Expanded for Dynamic Trading Pool / Opportunity Pool selection (DYNAMIC-POOL-SELECTION-001)


def load_x_sentiment_scores(
    universe: Optional[List[str]] = None,
    cache_path: str = X_CACHE,
    min_confidence: float = 0.15,
    min_posts: int = 5
) -> Dict[str, float]:
    """
    Load real X/Twitter sentiment from its dedicated cache.

    Preferred source. Real fetched data only.

    New richer format support (post_count, confidence, buzz_factor):
    - Low post count (< min_posts) or very low confidence is heavily damped toward 0
      (addresses statistical significance concern).
    - Buzz/volume is already baked into the stored "sentiment" value by the fetcher.
    """
    if universe is None:
        universe = DEFAULT_UNIVERSE

    scores: Dict[str, float] = {pair: 0.0 for pair in universe}

    if not os.path.exists(cache_path):
        logger.warning(f"X sentiment cache not found at {cache_path}.")
        return scores

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        for pair in universe:
            if pair in data:
                entry = data[pair]
                if isinstance(entry, dict):
                    raw_sent = entry.get("sentiment", entry.get("score", 0.0))
                    post_count = entry.get("post_count", entry.get("posts", 0))
                    confidence = entry.get("confidence", 1.0)

                    val = float(raw_sent)

                    # Statistical significance gate + low-confidence damping
                    if post_count < min_posts or confidence < min_confidence:
                        # Damp weak signals (prevents noisy low-volume pairs from moving the needle much)
                        damping = max(0.1, min(1.0, confidence * (post_count / max(min_posts, 1))))
                        val = val * damping

                    scores[pair] = val
                else:
                    scores[pair] = float(entry)
        return scores
    except Exception as e:
        logger.error(f"Failed to load X sentiment cache: {e}")
        return scores


def load_x_sentiment_details(
    universe: Optional[List[str]] = None,
    cache_path: str = X_CACHE
) -> Dict[str, dict]:
    """Return the full rich X data (sentiment + post_count + buzz + confidence) for a basket."""
    if universe is None:
        universe = DEFAULT_UNIVERSE

    details = {pair: {"sentiment": 0.0, "post_count": 0, "buzz_factor": 1.0, "confidence": 0.0} for pair in universe}

    if not os.path.exists(cache_path):
        return details

    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        for pair in universe:
            if pair in data and isinstance(data[pair], dict):
                details[pair] = {
                    "sentiment": float(data[pair].get("sentiment", 0.0)),
                    "post_count": int(data[pair].get("post_count", 0)),
                    "buzz_factor": float(data[pair].get("buzz_factor", 1.0)),
                    "confidence": float(data[pair].get("confidence", 0.0))
                }
        return details
    except Exception:
        return details


def _load_reddit_from_db(universe: List[str]) -> Dict[str, float]:
    """Query DB for latest Reddit/Apify sentiment per pair (shared cache for any trader).

    Only return value if the Apify return result was NOT empty (posts > 0 or real fetch occurred).
    If empty result (no posts or below threshold), return 0.0 meaning "no Reddit signal" (do not treat as neutral).
    This allows using Reddit when it provides value (backtest ROI benefit) but dropping when empty.
    """
    scores: Dict[str, float] = {pair: 0.0 for pair in universe}
    db_path = "/home/brad/projects/crypto-trading-bot/data/phase6.db"
    try:
        conn = __import__("sqlite3").connect(db_path)
        cur = conn.cursor()
        for pair in universe:
            cur.execute("""
                SELECT score, posts, source FROM sentiment_scores 
                WHERE pair = ? 
                ORDER BY ts DESC LIMIT 1
            """, (pair,))
            row = cur.fetchone()
            if row:
                score, posts, source = row
                # Only use if real result returned (posts > 0 or source indicates actual fetch)
                if posts is not None and posts > 0:
                    scores[pair] = float(score) if score is not None else 0.0
                elif source and "apify" in str(source).lower() or "reddit" in str(source).lower():
                    # Had a fetch but low/empty posts — treat as no signal (per clarification)
                    scores[pair] = 0.0
                else:
                    scores[pair] = float(score) if score is not None else 0.0
        conn.close()
    except Exception as e:
        logger.debug(f"DB Reddit load skipped or failed: {e}")
    return scores


def load_sentiment_scores(
    universe: Optional[List[str]] = None,
    cache_path: str = CANONICAL_CACHE
) -> Dict[str, float]:
    """
    Load sentiment for a (dynamic) trading basket.

    - Pulls the list of pairs from the caller's basket (trader-specific).
    - X is primary (real data).
    - Reddit/Apify: ONLY used if the return result had real data (posts > 0 in DB).
      If Apify result was empty (no/low posts), drop it — do not inject 0.0 as "Neutral".
      When Reddit returns values, it IS used (improved backtest ROI).
    - Values are in DB (rsi_values, sentiment_scores) so any trader with similar basket
      can query the cached pair-level data without re-fetching.
    - Fixes key mismatch in file cache as secondary fallback.
    """
    if universe is None:
        universe = DEFAULT_UNIVERSE

    # 1. X as primary real signal
    scores = load_x_sentiment_scores(universe)

    # 2. Reddit only when it actually returned data (from shared DB cache)
    reddit_scores = _load_reddit_from_db(universe)
    for pair in universe:
        if scores.get(pair, 0.0) == 0.0 and reddit_scores.get(pair, 0.0) != 0.0:
            # No X, but Reddit had real non-empty result -> use it
            scores[pair] = reddit_scores[pair]
        # If Reddit was empty result, we leave as 0.0 (no false neutral)

    # 3. Fallback to file canonical for any remaining (transition / key fix)
    pairs_still_zero = [p for p in universe if scores.get(p, 0.0) == 0.0]
    if pairs_still_zero and os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            schema_ver = data.get("schema_version", 0)
            try:
                schema_ver = int(schema_ver)
            except:
                schema_ver = 0
            if schema_ver >= 3:
                block = data.get("sentiment") or data.get("data", {})
                for pair in pairs_still_zero:
                    if pair in block:
                        entry = block[pair]
                        val = entry.get("score", entry.get("sentiment", 0.0)) if isinstance(entry, dict) else entry
                        # Conservative: only take if looks like real (not blindly 0 from empty)
                        if val != 0.0:
                            scores[pair] = float(val)
        except Exception:
            pass

    logger.info(f"Sentiment loaded for dynamic basket ({len(universe)} pairs). X primary; Reddit only on real results.")
    return scores


def load_latest_sentiment_for_basket(basket: List[str]) -> Dict[str, float]:
    """Convenience for runner/rebalancer: query cached RSI + Sentiment for a trader's basket from DB (shared)."""
    # RSI from DB
    rsi = {}
    db_path = "/home/brad/projects/crypto-trading-bot/data/phase6.db"
    try:
        conn = __import__("sqlite3").connect(db_path)
        cur = conn.cursor()
        for pair in basket:
            cur.execute("SELECT value FROM rsi_values WHERE pair=? ORDER BY ts DESC LIMIT 1", (pair,))
            row = cur.fetchone()
            if row:
                rsi[pair] = row[0]
        conn.close()
    except Exception:
        pass
    sent = load_sentiment_scores(universe=basket)
    return {"sentiment": sent, "rsi": rsi}


def get_sentiment_timestamp(cache_path: str = CANONICAL_CACHE) -> Optional[str]:
    """Return the timestamp of the last successful sentiment update, or None."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path) as f:
            data = json.load(f)
        return data.get("timestamp")
    except Exception:
        return None


def get_sentiment_freshness_minutes(cache_path: str = CANONICAL_CACHE) -> Optional[float]:
    """Return age of the sentiment data in minutes (for staleness checks in loops)."""
    ts = get_sentiment_timestamp(cache_path)
    if not ts:
        return None
    try:
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (now - last).total_seconds() / 60.0
        return round(delta, 1)
    except Exception:
        return None


def get_aged_sentiment_scores(
    universe: Optional[List[str]] = None,
    half_life_minutes: float = 60.0,
    cache_path: str = CANONICAL_CACHE
) -> Dict[str, float]:
    """
    Load scores and apply exponential aging/decay based on data age.

    Appropriate for conservative trading decisions: stale sentiment has reduced impact.
    decay = 2 ** (-age_minutes / half_life_minutes)
    Default half-life 60 minutes (matches historical grid-validated configs).
    Returns aged scores (can be negative or near-zero for very stale positive/negative).
    """
    raw = load_sentiment_scores(universe, cache_path)
    age = get_sentiment_freshness_minutes(cache_path) or 0.0

    if age <= 0:
        return raw

    decay = 2 ** (-age / half_life_minutes)
    aged = {p: round(s * decay, 4) for p, s in raw.items()}

    logger.info(
        f"Applied sentiment aging: age={age}min, half_life={half_life_minutes}min, "
        f"decay_factor={decay:.3f}"
    )
    return aged


def get_sentiment_adjusted_weights(
    base_weights: Dict[str, float],
    sentiment_scores: Dict[str, float],
    sentiment_weight: float = 0.2
) -> Dict[str, float]:
    """
    Simple, reliable adjustment: positive sentiment increases weight, negative decreases.
    Keeps weights summing to 1.0 with a small floor.
    Recommend passing aged scores for production safety.
    """
    if not base_weights:
        return {}

    adjusted = {}
    total = 0.0
    for pair, base_w in base_weights.items():
        sent = sentiment_scores.get(pair, 0.0)
        adj = base_w * (1.0 + sentiment_weight * sent)
        adjusted[pair] = max(0.01, adj)
        total += adjusted[pair]

    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted


# ============================================================
# Formatting helpers (used by intelligence reports and dashboards)
# ============================================================

def format_sentiment_label(score: float) -> str:
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


def format_sentiment_for_report(scores: Dict[str, float]) -> str:
    parts = []
    for pair, score in scores.items():
        label = format_sentiment_label(score)
        short = pair.replace("-USD", "")
        parts.append(f"{short}: {score:+.2f} ({label})")
    return " | ".join(parts)


def format_rsi_label(rsi: float) -> str:
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


def format_rsi_for_report(rsi_values: Dict[str, float]) -> str:
    parts = []
    for pair, rsi in rsi_values.items():
        label = format_rsi_label(rsi)
        short = pair.replace("-USD", "")
        parts.append(f"{short}: {rsi:.1f} ({label})")
    return " | ".join(parts)


if __name__ == "__main__":
    print("Raw scores:")
    print(load_sentiment_scores())
    print("\nAged scores (half-life 60min):")
    print(get_aged_sentiment_scores())
    print("\nFreshness (minutes ago):", get_sentiment_freshness_minutes())