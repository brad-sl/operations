#!/usr/bin/env python3
"""
Canonical Sentiment Scorer / Loader (single source of truth)

All trading logic, reports, and dashboards MUST use this module
to retrieve current sentiment scores.

- Primary: X cache + Reddit gate + canonical file
- Free hybrid fallback when X empty/spend-cap
  (config sentiment.primary=x_with_free_fallback | free_hybrid | x | off)
- Always returns scores for the requested universe (dynamic basket)
- Aging helper (exponential decay, half-life 60min default)
- Real data only (no placeholder fabrication)

Consumers:
- phase6 runner, backtests, deploy logic, paper harness
- intelligence reports
- live dashboards (serve_dashboard / serve_live_8501)
- any future loops or signal generators
"""

from .paths import (
    PROJECT_ROOT,
    SENTIMENT_CACHE,
    X_SENTIMENT_CACHE,
    FREE_SENTIMENT_CACHE,
    TRADING_CONFIG_PHASE6,
    load_trading_basket,
)  # per DATA_FLOW_AND_LOCATIONS.md

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CANONICAL_CACHE = str(SENTIMENT_CACHE)
X_CACHE = str(X_SENTIMENT_CACHE)
FREE_CACHE = str(FREE_SENTIMENT_CACHE)

DEFAULT_UNIVERSE = load_trading_basket()  # Dynamic from config via paths.py; falls back to 11.


def _load_sentiment_policy() -> Dict[str, Any]:
    """Read sentiment.primary / free_fallback flags from trading_config_phase6.json."""
    defaults = {
        "primary": "x_with_free_fallback",
        "free_fallback_when_x_empty": True,
        "x_min_usable_posts_total": 1,
        "free_max_age_hours": 18,
    }
    try:
        cfg_path = Path(TRADING_CONFIG_PHASE6)
        if not cfg_path.exists():
            return defaults
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        block = raw.get("sentiment") or {}
        out = dict(defaults)
        out.update({k: block[k] for k in defaults if k in block})
        env_p = os.environ.get("SENTIMENT_PRIMARY", "").strip()
        if env_p:
            out["primary"] = env_p
        env_fb = os.environ.get("SENTIMENT_FREE_FALLBACK", "").strip().lower()
        if env_fb in ("0", "false", "off", "no"):
            out["free_fallback_when_x_empty"] = False
        elif env_fb in ("1", "true", "on", "yes"):
            out["free_fallback_when_x_empty"] = True
        return out
    except Exception as e:
        logger.debug(f"sentiment policy load failed: {e}")
        return defaults


def _cache_age_hours(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    except Exception:
        return None


def load_free_sentiment_scores(
    universe: Optional[List[str]] = None,
    cache_path: str = FREE_CACHE,
    max_age_hours: float = 18.0,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Load free hybrid cache (funding + RSS + F&G). Returns (scores, meta)."""
    if universe is None:
        universe = DEFAULT_UNIVERSE
    scores: Dict[str, float] = {pair: 0.0 for pair in universe}
    meta: Dict[str, Any] = {"available": False, "timestamp": None, "sources": []}
    if not os.path.exists(cache_path):
        return scores, meta
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        ts = data.get("timestamp")
        age_h = _cache_age_hours(ts)
        if age_h is not None and age_h > max_age_hours:
            logger.warning(f"Free sentiment cache stale age_h={age_h:.1f} > {max_age_hours}")
            meta.update({"available": False, "timestamp": ts, "stale": True, "age_hours": age_h})
            return scores, meta
        block = data.get("sentiment") or data.get("data") or {}
        for pair in universe:
            entry = block.get(pair)
            if entry is None:
                continue
            if isinstance(entry, dict):
                val = entry.get("sentiment_score", entry.get("score", entry.get("sentiment", 0.0)))
            else:
                val = entry
            try:
                scores[pair] = float(val or 0.0)
            except (TypeError, ValueError):
                scores[pair] = 0.0
        m = data.get("meta") or {}
        meta = {
            "available": True,
            "timestamp": ts,
            "age_hours": age_h,
            "sources": m.get("sources_used") or [],
            "mode": m.get("mode"),
            "fng_value": m.get("fng_value"),
            "non_zero": sum(1 for v in scores.values() if abs(v) > 1e-9),
        }
        return scores, meta
    except Exception as e:
        logger.error(f"Failed to load free sentiment cache: {e}")
        return scores, meta


def x_signal_usable(
    universe: Optional[List[str]] = None,
    cache_path: str = X_CACHE,
    min_posts_total: int = 1,
) -> Dict[str, Any]:
    """Whether X cache has enough real posts to prefer over free fallback."""
    if universe is None:
        universe = DEFAULT_UNIVERSE
    total_posts = 0
    nz = 0
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            for pair in universe:
                entry = data.get(pair) or {}
                if not isinstance(entry, dict):
                    continue
                posts = int(entry.get("post_count", entry.get("posts", 0)) or 0)
                total_posts += max(0, posts)
                try:
                    s = float(entry.get("sentiment", entry.get("score", 0.0)) or 0.0)
                except (TypeError, ValueError):
                    s = 0.0
                if abs(s) > 1e-9 and posts > 0:
                    nz += 1
        except Exception:
            pass
    usable = total_posts >= int(min_posts_total)
    return {"usable": usable, "total_posts": total_posts, "non_zero_with_posts": nz}


def load_x_sentiment_scores(
    universe: Optional[List[str]] = None,
    cache_path: str = X_CACHE,
    min_confidence: float = 0.15,
    min_posts: int = 5
) -> Dict[str, float]:
    """
    Load real X/Twitter sentiment from its dedicated cache.

    Preferred source when posts exist. Low post count / confidence is damped.
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

                    if post_count < min_posts or confidence < min_confidence:
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
                    "confidence": float(data[pair].get("confidence", 0.0)),
                    "timestamp": data[pair].get("timestamp"),
                }
        return details
    except Exception:
        return details


def _load_reddit_from_db(universe: List[str]) -> Dict[str, float]:
    """Query DB for latest Reddit/Apify sentiment per pair (shared cache).

    Only return value if posts > 0. Empty Apify results are not treated as Neutral signal.
    """
    scores: Dict[str, float] = {pair: 0.0 for pair in universe}
    db_path = str(PROJECT_ROOT / "data/phase6.db")
    try:
        conn = __import__("sqlite3").connect(db_path)
        cur = conn.cursor()
        for pair in universe:
            cur.execute(
                """
                SELECT score, posts, source FROM sentiment_scores
                WHERE pair = ?
                ORDER BY ts DESC LIMIT 1
                """,
                (pair,),
            )
            row = cur.fetchone()
            if row:
                score, posts, source = row
                if posts is not None and posts > 0:
                    scores[pair] = float(score) if score is not None else 0.0
                elif source and ("apify" in str(source).lower() or "reddit" in str(source).lower()):
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

    Policy (config sentiment.primary / free_fallback_when_x_empty):
    - x: X primary, Reddit fill, canonical file fill; free only if free_fallback_when_x_empty
    - free_hybrid: free cache primary (funding+RSS+F&G)
    - x_with_free_fallback (default): X when usable posts; else free hybrid
    - off: zeros
    """
    detail = load_sentiment_scores_detailed(universe=universe, cache_path=cache_path)
    return {p: float(v.get("sentiment", 0.0)) for p, v in detail["scores"].items()}


def load_sentiment_scores_detailed(
    universe: Optional[List[str]] = None,
    cache_path: str = CANONICAL_CACHE,
) -> Dict[str, Any]:
    """Rich loader: per-pair sentiment + source + overall mode (for dashboard/runner)."""
    if universe is None:
        universe = DEFAULT_UNIVERSE

    policy = _load_sentiment_policy()
    primary = str(policy.get("primary") or "x_with_free_fallback").strip().lower()
    free_fb = bool(policy.get("free_fallback_when_x_empty", True))
    min_posts = int(policy.get("x_min_usable_posts_total", 1) or 1)
    free_max_age = float(policy.get("free_max_age_hours", 18) or 18)

    out_scores: Dict[str, Dict[str, Any]] = {
        p: {"sentiment": 0.0, "source": "none"} for p in universe
    }
    mode = "none"
    free_meta: Dict[str, Any] = {}
    x_info = x_signal_usable(universe, min_posts_total=min_posts)

    if primary == "off":
        return {
            "scores": out_scores,
            "mode": "off",
            "policy": policy,
            "free_meta": free_meta,
            "x_usable": x_info,
            "non_zero": 0,
        }

    def _set_all(m: Dict[str, float], src: str) -> None:
        for pair in universe:
            out_scores[pair] = {"sentiment": float(m.get(pair, 0.0) or 0.0), "source": src}

    use_free_primary = primary in ("free_hybrid", "free", "free_shadow")

    if use_free_primary:
        free_scores, free_meta = load_free_sentiment_scores(universe, max_age_hours=free_max_age)
        if free_meta.get("available") and free_meta.get("non_zero", 0) > 0:
            _set_all(free_scores, "free_hybrid")
            mode = "free_hybrid"
        else:
            mode = "free_hybrid_empty"
    else:
        # X primary path
        x_scores = load_x_sentiment_scores(universe)
        if x_info.get("usable"):
            _set_all(x_scores, "x")
            mode = "x"
        else:
            mode = "x_empty"

        # Reddit fill zeros only
        reddit_scores = _load_reddit_from_db(universe)
        for pair in universe:
            if abs(out_scores[pair]["sentiment"]) <= 1e-9 and abs(reddit_scores.get(pair, 0.0)) > 1e-9:
                out_scores[pair] = {"sentiment": float(reddit_scores[pair]), "source": "reddit"}

        # Canonical file fill
        pairs_still_zero = [p for p in universe if abs(out_scores[p]["sentiment"]) <= 1e-9]
        if pairs_still_zero and os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                schema_ver = data.get("schema_version", 0)
                try:
                    schema_ver = int(schema_ver)
                except Exception:
                    schema_ver = 0
                block = data.get("sentiment") or data.get("data", {}) if schema_ver >= 3 else data
                meta_src = (data.get("meta") or {}).get("source") or ""
                for pair in pairs_still_zero:
                    if pair not in block:
                        continue
                    entry = block[pair]
                    if isinstance(entry, dict):
                        val = entry.get(
                            "sentiment_score",
                            entry.get("score", entry.get("sentiment", 0.0)),
                        )
                        src = entry.get("source") or (
                            "canonical_free" if "free" in str(meta_src) else "canonical"
                        )
                    else:
                        val = entry
                        src = "canonical"
                    try:
                        fv = float(val or 0.0)
                    except (TypeError, ValueError):
                        fv = 0.0
                    if abs(fv) > 1e-9:
                        out_scores[pair] = {"sentiment": fv, "source": src}
            except Exception:
                pass

        # Free hybrid fallback when X unusable / still all zero
        use_free_fallback = free_fb and primary in (
            "x_with_free_fallback",
            "x+free",
            "x_free_fallback",
            "x",
        )
        need_free = use_free_fallback and (
            not x_info.get("usable")
            or sum(1 for p in universe if abs(out_scores[p]["sentiment"]) > 1e-9) == 0
        )
        if need_free:
            free_scores, free_meta = load_free_sentiment_scores(universe, max_age_hours=free_max_age)
            if free_meta.get("available") and free_meta.get("non_zero", 0) > 0:
                if not x_info.get("usable"):
                    _set_all(free_scores, "free_fallback")
                    mode = "free_fallback"
                else:
                    filled = 0
                    for pair in universe:
                        fv = float(free_scores.get(pair, 0.0) or 0.0)
                        if abs(out_scores[pair]["sentiment"]) <= 1e-9 and abs(fv) > 1e-9:
                            out_scores[pair] = {"sentiment": fv, "source": "free_fallback"}
                            filled += 1
                    if filled:
                        mode = "free_fallback_partial"
                logger.warning(
                    f"Using FREE sentiment fallback (X usable={x_info.get('usable')} "
                    f"posts={x_info.get('total_posts')} mode={mode})"
                )

    non_zero = sum(1 for v in out_scores.values() if abs(v["sentiment"]) > 1e-9)
    logger.info(
        f"Sentiment loaded for dynamic basket ({len(universe)} pairs). mode={mode} "
        f"non_zero={non_zero} x_posts={x_info.get('total_posts')}"
    )
    return {
        "scores": out_scores,
        "mode": mode,
        "policy": policy,
        "free_meta": free_meta,
        "x_usable": x_info,
        "non_zero": non_zero,
    }


def load_latest_sentiment_for_basket(
    basket: List[str],
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Convenience for runner/rebalancer: RSI from DB + sentiment via canonical loader."""
    rsi = {}
    db_path = str(PROJECT_ROOT / "data/phase6.db")
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
    sent = sentiment_scores if sentiment_scores is not None else load_sentiment_scores(universe=basket)
    return {"sentiment": sent, "rsi": rsi}


def get_sentiment_timestamp(cache_path: str = CANONICAL_CACHE) -> Optional[str]:
    """Return the timestamp of the active sentiment source (X/canonical or free fallback)."""
    policy = _load_sentiment_policy()
    primary = str(policy.get("primary") or "").lower()
    x_info = x_signal_usable(min_posts_total=int(policy.get("x_min_usable_posts_total", 1) or 1))
    use_free = primary in ("free_hybrid", "free", "free_shadow") or (
        bool(policy.get("free_fallback_when_x_empty", True)) and not x_info.get("usable")
    )
    if use_free and os.path.exists(FREE_CACHE):
        try:
            with open(FREE_CACHE) as f:
                data = json.load(f)
            ts = data.get("timestamp")
            if ts:
                return ts
        except Exception:
            pass
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
    cache_path: str = CANONICAL_CACHE,
    *,
    raw_scores: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Load scores and apply exponential aging/decay based on data age.

    decay = 2 ** (-age_minutes / half_life_minutes)
    Default half-life 60 minutes.
    """
    raw = raw_scores if raw_scores is not None else load_sentiment_scores(universe, cache_path)
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
    """Positive sentiment increases weight, negative decreases. Sums to 1.0 with floor."""
    if not base_weights:
        return {}

    adjusted = {}
    total = 0.0
    for pair, base_w in base_weights.items():
        sent = sentiment_scores.get(pair, 0.0)
        if isinstance(sent, dict):
            sent = float(sent.get("sentiment", sent.get("combined", 0.0)) or 0.0)
        adj = base_w * (1.0 + sentiment_weight * float(sent))
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
        if isinstance(score, dict):
            score = float(score.get("sentiment", score.get("combined", 0.0)) or 0.0)
        label = format_sentiment_label(float(score))
        short = pair.replace("-USD", "")
        parts.append(f"{short}: {float(score):+.2f} ({label})")
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
    d = load_sentiment_scores_detailed()
    print("mode:", d["mode"], "non_zero:", d["non_zero"], "x_usable:", d["x_usable"])
    print("Raw scores:")
    print(load_sentiment_scores())
    print("\nDetailed (sample):")
    for p, e in list(d["scores"].items())[:6]:
        print(f"  {p}: {e}")
    print("\nAged scores (half-life 60min):")
    print(get_aged_sentiment_scores())
    print("\nFreshness (minutes ago):", get_sentiment_freshness_minutes())
