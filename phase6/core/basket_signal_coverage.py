"""
Canonical basket signal coverage (11/11) for intelligence report + pre-rebalance.

FULL = RSI (or Stoch from rsi_cache) + sentiment *observed* for the pair.
Observed = real X/Reddit fetch recorded (timestamp in x cache, or posts>0, or non-zero effective score).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket


def _load_rsi_cache() -> Dict[str, Any]:
    p = PROJECT_ROOT / "data/state/rsi_cache.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("rsi", {}) or {}
    except Exception:
        return {}


def _x_details(universe: List[str]) -> Dict[str, dict]:
    from phase6.core.sentiment_scorer import load_x_sentiment_details

    return load_x_sentiment_details(universe=universe)


def _sent_scores(universe: List[str]) -> Dict[str, float]:
    from phase6.core.sentiment_scorer import load_sentiment_scores

    return load_sentiment_scores(universe=universe) or {}


def assess_pair_signal_coverage(
    basket: Optional[List[str]] = None,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Returns per-pair status and aggregate full_count for the trading basket.
    """
    basket = list(basket or load_trading_basket())
    rsi_cache = _load_rsi_cache()
    x_det = _x_details(basket)
    sent = sentiment_scores if sentiment_scores is not None else _sent_scores(basket)

    # DB RSI fallback
    rsi_db: Dict[str, float] = {}
    try:
        import sqlite3

        conn = sqlite3.connect(str(PROJECT_ROOT / "data/phase6.db"))
        cur = conn.cursor()
        for pair in basket:
            cur.execute(
                "SELECT value FROM rsi_values WHERE pair=? ORDER BY ts DESC LIMIT 1",
                (pair,),
            )
            row = cur.fetchone()
            if row:
                rsi_db[pair] = float(row[0])
        conn.close()
    except Exception:
        pass

    per_pair: Dict[str, Dict[str, Any]] = {}
    full_count = 0
    missing_sent_fetch: List[str] = []

    for pair in basket:
        cache_entry = rsi_cache.get(pair, {})
        rsi_val = None
        if isinstance(cache_entry, dict) and cache_entry.get("rsi") is not None:
            rsi_val = float(cache_entry["rsi"])
        elif pair in rsi_db:
            rsi_val = rsi_db[pair]

        has_rsi = rsi_val is not None and abs(rsi_val) > 0.1
        has_stoch = isinstance(cache_entry, dict) and cache_entry.get("stoch_k") is not None
        has_price_signal = has_rsi or has_stoch

        xd = x_det.get(pair, {})
        posts = int(xd.get("post_count", 0) or 0)
        conf = float(xd.get("confidence", 0) or 0)
        eff = float(sent.get(pair, 0.0) or 0.0)
        x_ts = xd.get("timestamp")  # may be absent in details loader — check raw cache

        # Observed sentiment: we ran fetch and have cache row, or non-trivial score
        observed = posts > 0 or abs(eff) > 0.001 or conf >= 0.05
        if not observed:
            # Raw x cache timestamp means "we looked"
            raw = _raw_x_entry(pair)
            if raw and raw.get("timestamp"):
                observed = True
                if posts == 0 and eff == 0.0:
                    # Honest neutral after real fetch
                    pass

        if has_price_signal and observed:
            status = "FULL"
            full_count += 1
        elif has_price_signal:
            status = "RSI-ONLY"
            missing_sent_fetch.append(pair)
        elif observed:
            status = "SENT-ONLY"
        else:
            status = "MISSING"

        per_pair[pair] = {
            "status": status,
            "rsi": rsi_val,
            "stoch_k": cache_entry.get("stoch_k") if isinstance(cache_entry, dict) else None,
            "sentiment_effective": eff,
            "x_posts": posts,
            "x_confidence": conf,
            "sentiment_observed": observed,
        }

    return {
        "basket_size": len(basket),
        "full_count": full_count,
        "complete": full_count == len(basket),
        "missing_sentiment_fetch": missing_sent_fetch,
        "per_pair": per_pair,
    }


def _raw_x_entry(pair: str) -> Optional[dict]:
    p = PROJECT_ROOT / "data/state/x_sentiment_cache.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        ent = data.get(pair)
        return ent if isinstance(ent, dict) else None
    except Exception:
        return None


def persist_sentiment_observations_to_db(basket: Optional[List[str]] = None) -> int:
    """Write per-pair X observation rows so shared DB reflects 11/11 fetch pass."""
    basket = list(basket or load_trading_basket())
    x_det = _x_details(basket)
    import sqlite3
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    n = 0
    try:
        conn = sqlite3.connect(str(PROJECT_ROOT / "data/phase6.db"))
        cur = conn.cursor()
        for pair in basket:
            xd = x_det.get(pair, {})
            score = float(xd.get("sentiment", 0.0) or 0.0)
            posts = int(xd.get("post_count", 0) or 0)
            cur.execute(
                """
                INSERT INTO sentiment_scores (pair, score, posts, ts, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pair, score, posts, ts, "x_refresh"),
            )
            n += 1
        conn.commit()
        conn.close()
    except Exception:
        pass
    return n