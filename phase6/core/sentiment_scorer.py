#!/usr/bin/env python3
"""
Canonical Sentiment Scorer / Loader (single source of truth)

All trading logic, reports, and dashboards MUST use this module
to retrieve current sentiment scores.

- Primary: X cache when fresh/usable
- **Complete clock (Brad GO 2026-09-05):** when X is aged-out or unavailable,
  revert to **latest Reddit** score (Hermes reddit-reading cache; 60m HL).
  Free hybrid + Adanos stay **shadow** / emergency-only — not the mid-cycle bridge.
- Free hybrid fallback only when X empty/spend-cap **and** Reddit also empty
  (config sentiment.primary=x_with_free_fallback | free_hybrid | x | off)
- Always returns scores for the requested universe (dynamic basket)
- **Source-aware exponential aging (default ON)** — grid-optimal 2026-04-21:
  X / twitter half-life **15 min** (highly transitory); Reddit **60 min** (hour bridge).
  Free hybrid uses **60 min** HL when it is the live emergency source.
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
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CANONICAL_CACHE = str(SENTIMENT_CACHE)
X_CACHE = str(X_SENTIMENT_CACHE)
FREE_CACHE = str(FREE_SENTIMENT_CACHE)
# Live Reddit bridge (Hermes reddit-reading skill) — not Adanos/free shadow
REDDIT_READING_CACHE = str(PROJECT_ROOT / "data/state/sentiment_cache_reddit_reading.json")
try:
    from .paths import REDDIT_SENTIMENT_CACHE as _REDDIT_LEGACY_PATH  # type: ignore

    REDDIT_LEGACY_CACHE = str(_REDDIT_LEGACY_PATH)
except Exception:
    REDDIT_LEGACY_CACHE = str(PROJECT_ROOT / "data/state/reddit_sentiment_cache.json")

# Snapshot only for rare callers that import the name; live loads must re-read
# config (dashboard/runner stay up across basket promotes).
DEFAULT_UNIVERSE = load_trading_basket()  # may be stale in long-lived processes


def _load_sentiment_policy() -> Dict[str, Any]:
    """Read sentiment.primary / free_fallback / aging flags from trading_config_phase6.json."""
    # Half-lives from config/sentiment_grid_results_20260421_151742/SUMMARY.json optimal:
    # twitter 15m (transitory) + reddit 60m (hour bridge). Brad 2026-09-04: raw unaged
    # live path was a bug — aging must bind decision loads by default.
    defaults = {
        "primary": "x_with_free_fallback",
        "free_fallback_when_x_empty": True,
        "x_min_usable_posts_total": 1,
        "free_max_age_hours": 18,
        "apply_aging": True,
        "x_half_life_minutes": 15.0,
        "reddit_half_life_minutes": 60.0,
        "free_half_life_minutes": 60.0,
        "canonical_half_life_minutes": 15.0,
        "x_staleness_zero_minutes": 120.0,
        "reddit_staleness_zero_minutes": 240.0,
        "free_staleness_zero_minutes": 360.0,
        # Complete clock: hand X → Reddit when X faded or missing (Brad GO 2026-09-05)
        "reddit_bridge_when_x_aged_out": True,
        "x_aged_out_decay_max": 0.15,  # ~45m at 15m HL
        "x_aged_out_age_min_minutes": 45.0,
        "reddit_bridge_max_age_hours": 8.0,
    }
    try:
        cfg_path = Path(TRADING_CONFIG_PHASE6)
        if not cfg_path.exists():
            return defaults
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        block = raw.get("sentiment") or {}
        out = dict(defaults)
        for k in defaults:
            if k in block:
                out[k] = block[k]
        env_p = os.environ.get("SENTIMENT_PRIMARY", "").strip()
        if env_p:
            out["primary"] = env_p
        env_fb = os.environ.get("SENTIMENT_FREE_FALLBACK", "").strip().lower()
        if env_fb in ("0", "false", "off", "no"):
            out["free_fallback_when_x_empty"] = False
        elif env_fb in ("1", "true", "on", "yes"):
            out["free_fallback_when_x_empty"] = True
        env_age = os.environ.get("SENTIMENT_APPLY_AGING", "").strip().lower()
        if env_age in ("0", "false", "off", "no"):
            out["apply_aging"] = False
        elif env_age in ("1", "true", "on", "yes"):
            out["apply_aging"] = True
        return out
    except Exception as e:
        logger.debug(f"sentiment policy load failed: {e}")
        return defaults


def _parse_ts_utc(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last.astimezone(timezone.utc)
    except Exception:
        return None


def _cache_age_hours(ts: Optional[str]) -> Optional[float]:
    last = _parse_ts_utc(ts)
    if last is None:
        return None
    try:
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    except Exception:
        return None


def _age_minutes(ts: Optional[str]) -> Optional[float]:
    last = _parse_ts_utc(ts)
    if last is None:
        return None
    try:
        return max(0.0, (datetime.now(timezone.utc) - last).total_seconds() / 60.0)
    except Exception:
        return None


def _exponential_decay_factor(
    age_minutes: Optional[float],
    half_life_minutes: float,
    staleness_zero_minutes: Optional[float] = None,
) -> float:
    """decay = 0.5 ** (age / half_life). Age past staleness → 0 (neutral)."""
    if age_minutes is None:
        return 0.0
    if age_minutes <= 0:
        return 1.0
    hl = float(half_life_minutes or 0.0)
    if hl <= 0:
        return 1.0
    if staleness_zero_minutes is not None and age_minutes > float(staleness_zero_minutes):
        return 0.0
    return float(max(0.0, min(1.0, math.pow(0.5, age_minutes / hl))))


def _half_life_for_source(source: str, policy: Dict[str, Any]) -> Tuple[float, Optional[float]]:
    """Return (half_life_min, staleness_zero_min) for a resolved source label."""
    s = str(source or "").lower()
    if s in ("x", "twitter", "x_primary"):
        return (
            float(policy.get("x_half_life_minutes", 15.0) or 15.0),
            float(policy.get("x_staleness_zero_minutes", 120.0) or 120.0),
        )
    if "reddit" in s or "apify" in s:
        return (
            float(policy.get("reddit_half_life_minutes", 60.0) or 60.0),
            float(policy.get("reddit_staleness_zero_minutes", 240.0) or 240.0),
        )
    if "free" in s:
        return (
            float(policy.get("free_half_life_minutes", 60.0) or 60.0),
            float(policy.get("free_staleness_zero_minutes", 360.0) or 360.0),
        )
    # canonical / unknown → treat as X-shaped (transitory) unless labeled free
    return (
        float(policy.get("canonical_half_life_minutes", 15.0) or 15.0),
        float(policy.get("x_staleness_zero_minutes", 120.0) or 120.0),
    )


def _x_pair_timestamp(pair: str, cache_path: Optional[str] = None) -> Optional[str]:
    if cache_path is None:
        cache_path = X_CACHE
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        entry = data.get(pair) if isinstance(data, dict) else None
        if isinstance(entry, dict):
            return entry.get("timestamp") or entry.get("fetched_at") or entry.get("ts")
        # some caches nest under sentiment
        block = data.get("sentiment") or data.get("data") or {}
        if isinstance(block, dict):
            e2 = block.get(pair)
            if isinstance(e2, dict):
                return e2.get("timestamp") or e2.get("fetched_at")
        return data.get("timestamp") if isinstance(data, dict) else None
    except Exception:
        return None


def _source_timestamp(
    pair: str,
    source: str,
    *,
    free_meta: Optional[Dict[str, Any]] = None,
    cache_path: Optional[str] = None,
    x_cache_path: Optional[str] = None,
) -> Optional[str]:
    if cache_path is None:
        cache_path = CANONICAL_CACHE
    if x_cache_path is None:
        x_cache_path = X_CACHE
    s = str(source or "").lower()
    if s in ("x", "twitter", "x_primary"):
        return _x_pair_timestamp(pair, cache_path=x_cache_path) or get_sentiment_timestamp(cache_path)
    if "free" in s:
        if free_meta and free_meta.get("timestamp"):
            return str(free_meta.get("timestamp"))
        try:
            if os.path.exists(FREE_CACHE):
                with open(FREE_CACHE) as f:
                    return json.load(f).get("timestamp")
        except Exception:
            pass
        return None
    if "reddit" in s or "apify" in s:
        # Prefer live bridge cache (reddit-reading), then legacy Apify file
        for rp in (REDDIT_READING_CACHE, REDDIT_LEGACY_CACHE):
            try:
                if not os.path.exists(rp):
                    continue
                with open(rp) as f:
                    rd = json.load(f)
                block = rd.get("sentiment") if isinstance(rd.get("sentiment"), dict) else None
                e = None
                if block and pair in block and isinstance(block[pair], dict):
                    e = block[pair]
                elif isinstance(rd.get(pair), dict):
                    e = rd.get(pair)
                if isinstance(e, dict) and (e.get("timestamp") or e.get("fetched_at")):
                    return e.get("timestamp") or e.get("fetched_at")
                if isinstance(rd, dict) and rd.get("timestamp"):
                    return rd.get("timestamp")
            except Exception:
                continue
        return get_sentiment_timestamp(cache_path)
    return get_sentiment_timestamp(cache_path)


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
    cache_path: Optional[str] = None,
    min_posts_total: int = 1,
) -> Dict[str, Any]:
    """Whether X cache has enough real posts to prefer over free fallback."""
    if cache_path is None:
        cache_path = X_CACHE
    if universe is None:
        try:
            universe = list(load_trading_basket() or []) or list(DEFAULT_UNIVERSE)
        except Exception:
            universe = list(DEFAULT_UNIVERSE)
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
    cache_path: Optional[str] = None,
    min_confidence: float = 0.15,
    min_posts: int = 5
) -> Dict[str, float]:
    """
    Load real X/Twitter sentiment from its dedicated cache.

    Preferred source when posts exist. Low post count / confidence is damped.
    """
    if cache_path is None:
        cache_path = X_CACHE
    if universe is None:
        try:
            universe = list(load_trading_basket() or []) or list(DEFAULT_UNIVERSE)
        except Exception:
            universe = list(DEFAULT_UNIVERSE)

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
    cache_path: Optional[str] = None
) -> Dict[str, dict]:
    """Return the full rich X data (sentiment + post_count + buzz + confidence) for a basket."""
    if cache_path is None:
        cache_path = X_CACHE
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



def _pair_score_from_entry(entry: Any) -> float:
    if entry is None:
        return 0.0
    if isinstance(entry, dict):
        val = entry.get(
            "sentiment_score",
            entry.get("score", entry.get("sentiment", 0.0)),
        )
    else:
        val = entry
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_latest_reddit_scores(
    universe: Optional[List[str]] = None,
    *,
    max_age_hours: float = 8.0,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Latest Reddit scores for the complete-clock bridge.

    Preference order (live path — Adanos/free stay shadow):
      1) Hermes reddit-reading cache (Atom/OAuth skill)
      2) Legacy reddit_sentiment_cache.json if still fresh + non-zero
      3) DB reddit/apify rows (posts > 0)

    Returns (scores, meta). Does not invent scores.
    """
    if universe is None:
        try:
            universe = list(load_trading_basket() or []) or list(DEFAULT_UNIVERSE)
        except Exception:
            universe = list(DEFAULT_UNIVERSE)
    scores: Dict[str, float] = {p: 0.0 for p in universe}
    meta: Dict[str, Any] = {
        "available": False,
        "source": None,
        "timestamp": None,
        "path": None,
        "non_zero": 0,
    }

    def _from_file(path: str, label: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("reddit cache read fail %s: %s", path, e)
            return False
        ts = data.get("timestamp") or data.get("fetched_at") or data.get("as_of")
        age_h = _cache_age_hours(ts) if ts else None
        if age_h is not None and age_h > float(max_age_hours):
            logger.info(
                "Reddit cache stale label=%s age_h=%.2f > max=%.2f path=%s",
                label,
                age_h,
                max_age_hours,
                path,
            )
            return False
        block = data.get("sentiment") if isinstance(data.get("sentiment"), dict) else None
        local: Dict[str, float] = {}
        for pair in universe:
            if block and pair in block:
                local[pair] = _pair_score_from_entry(block.get(pair))
            elif pair in data:
                local[pair] = _pair_score_from_entry(data.get(pair))
            else:
                local[pair] = 0.0
        nz = sum(1 for v in local.values() if abs(v) > 1e-9)
        if nz <= 0 and label != "reddit_reading":
            # empty legacy file is not a signal
            return False
        scores.update(local)
        meta.update(
            {
                "available": nz > 0 or label == "reddit_reading",
                "source": label,
                "timestamp": ts,
                "path": path,
                "age_hours": age_h,
                "non_zero": nz,
            }
        )
        return nz > 0 or label == "reddit_reading"

    if _from_file(REDDIT_READING_CACHE, "reddit_reading"):
        return scores, meta
    if _from_file(REDDIT_LEGACY_CACHE, "reddit_legacy"):
        return scores, meta

    # DB last resort
    db_scores = _load_reddit_from_db(universe)
    nz = sum(1 for v in db_scores.values() if abs(v) > 1e-9)
    if nz > 0:
        scores.update(db_scores)
        meta.update(
            {
                "available": True,
                "source": "reddit_db",
                "timestamp": None,
                "path": "data/phase6.db",
                "non_zero": nz,
            }
        )
    return scores, meta


def _x_score_aged_out(info: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    """True when this pair's live X contribution should yield to Reddit bridge."""
    src = str(info.get("source") or "").lower()
    if src in ("none", ""):
        return True
    if src not in ("x", "twitter", "x_primary"):
        return False
    handoff_decay = float(policy.get("x_aged_out_decay_max", 0.15) or 0.15)
    handoff_age = float(policy.get("x_aged_out_age_min_minutes", 45.0) or 45.0)
    decay = info.get("decay_factor")
    age = info.get("age_min")
    aged = abs(float(info.get("sentiment", 0.0) or 0.0))
    raw = abs(float(info.get("sentiment_raw", info.get("sentiment", 0.0)) or 0.0))
    if decay is not None and float(decay) <= handoff_decay:
        return True
    if age is not None and float(age) >= handoff_age:
        return True
    if aged <= 1e-9 and raw > 1e-9:
        return True
    if aged <= 1e-9 and (decay is not None and float(decay) <= handoff_decay):
        return True
    return False


def _apply_reddit_bridge(
    out_scores: Dict[str, Dict[str, Any]],
    *,
    universe: List[str],
    policy: Dict[str, Any],
    x_info: Dict[str, Any],
    do_age: bool,
    mode: str,
) -> Tuple[str, Dict[str, Any]]:
    """When X aged-out or unavailable, revert pairs to latest Reddit (60m HL)."""
    bridge_meta: Dict[str, Any] = {
        "enabled": bool(policy.get("reddit_bridge_when_x_aged_out", True)),
        "bridged_pairs": 0,
        "source": None,
    }
    if not bridge_meta["enabled"]:
        return mode, bridge_meta

    max_age = float(policy.get("reddit_bridge_max_age_hours", 8.0) or 8.0)
    rr_scores, rr_meta = load_latest_reddit_scores(universe, max_age_hours=max_age)
    bridge_meta["reddit_meta"] = {
        k: rr_meta.get(k)
        for k in ("available", "source", "timestamp", "age_hours", "non_zero", "path")
    }
    if not rr_meta.get("available"):
        return mode, bridge_meta

    x_usable = bool(x_info.get("usable"))
    hl = float(policy.get("reddit_half_life_minutes", 60.0) or 60.0)
    stale_z = float(policy.get("reddit_staleness_zero_minutes", 240.0) or 240.0)
    rr_ts = rr_meta.get("timestamp")
    rr_label = str(rr_meta.get("source") or "reddit")
    src_tag = f"reddit_bridge:{rr_label}" if "reddit" not in rr_label else f"reddit_bridge"

    bridged = 0
    for pair in universe:
        info = out_scores.get(pair) or {"sentiment": 0.0, "source": "none"}
        need = False
        if not x_usable and abs(float(info.get("sentiment", 0.0) or 0.0)) <= 1e-9:
            need = True
        elif _x_score_aged_out(info, policy):
            need = True
        elif str(info.get("source") or "").lower() in ("none", "") and abs(
            float(info.get("sentiment", 0.0) or 0.0)
        ) <= 1e-9:
            need = True
        # Source priority after X fades: Reddit bridge > emergency free_fallback.
        # Do not clobber intentional free_hybrid primary or an existing reddit row.
        src = str(info.get("source") or "").lower()
        if src.startswith("reddit"):
            need = False
        elif ("free_hybrid" in src or src in ("free", "free_shadow")) and abs(
            float(info.get("sentiment", 0.0) or 0.0)
        ) > 1e-9:
            need = False
        elif "free_fallback" in src and abs(float(info.get("sentiment", 0.0) or 0.0)) > 1e-9:
            # Emergency free filled while X dead — prefer Reddit when available
            need = True

        if not need:
            continue
        raw_r = float(rr_scores.get(pair, 0.0) or 0.0)
        if abs(raw_r) <= 1e-9:
            # Reddit has no signal for this pair — clear dead X residue to Neutral
            if _x_score_aged_out(info, policy) or not x_usable:
                out_scores[pair] = {
                    "sentiment": 0.0,
                    "source": f"{src_tag}:empty",
                    "sentiment_raw": 0.0,
                    "decay_factor": 0.0,
                    "age_min": info.get("age_min"),
                    "half_life_min": hl,
                    "source_ts": rr_ts,
                    "bridge": "x_to_reddit_empty",
                    "prior_source": src or info.get("source"),
                    "prior_sentiment": info.get("sentiment"),
                }
                bridged += 1
            continue
        if do_age:
            age_m = _age_minutes(rr_ts)
            decay = _exponential_decay_factor(age_m, hl, stale_z)
            aged_v = raw_r * decay
        else:
            age_m = _age_minutes(rr_ts)
            decay = 1.0
            aged_v = raw_r
        # Only take bridge if reddit aged value is the handoff (always when X dead/aged)
        out_scores[pair] = {
            "sentiment": round(float(aged_v), 6),
            "source": src_tag,
            "sentiment_raw": round(float(raw_r), 6),
            "decay_factor": round(float(decay), 4),
            "age_min": round(age_m, 1) if age_m is not None else None,
            "half_life_min": hl,
            "source_ts": rr_ts,
            "bridge": "x_to_reddit",
            "prior_source": src or info.get("source"),
            "prior_sentiment": info.get("sentiment"),
        }
        bridged += 1

    bridge_meta["bridged_pairs"] = bridged
    bridge_meta["source"] = rr_label
    if bridged:
        if x_usable:
            mode = "x_reddit_bridge"
        else:
            mode = "reddit_bridge"
        logger.info(
            "Sentiment Reddit bridge ON bridged=%s/%s src=%s mode=%s",
            bridged,
            len(universe),
            rr_label,
            mode,
        )
    return mode, bridge_meta


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
    cache_path: str = CANONICAL_CACHE,
    *,
    apply_aging: Optional[bool] = None,
) -> Dict[str, float]:
    """
    Load sentiment for a (dynamic) trading basket.

    Policy (config sentiment.primary / free_fallback_when_x_empty):
    - x: X primary, Reddit fill, canonical file fill; free only if free_fallback_when_x_empty
    - free_hybrid: free cache primary (funding+RSS+F&G)
    - x_with_free_fallback (default): X when usable posts; else free hybrid
    - off: zeros

    By default returns **aged** scores (X 15m HL / Reddit 60m HL). Pass
    apply_aging=False for raw cache values (research / dash raw column only).
    """
    detail = load_sentiment_scores_detailed(
        universe=universe, cache_path=cache_path, apply_aging=apply_aging
    )
    return {p: float(v.get("sentiment", 0.0)) for p, v in detail["scores"].items()}


def load_sentiment_scores_detailed(
    universe: Optional[List[str]] = None,
    cache_path: str = CANONICAL_CACHE,
    *,
    apply_aging: Optional[bool] = None,
) -> Dict[str, Any]:
    """Rich loader: per-pair sentiment + source + overall mode (for dashboard/runner).

    When aging is on (default), each pair keeps sentiment_raw + decay metadata;
    `sentiment` is the decayed value used by decision paths.
    """
    if universe is None:
        # Always re-read basket — do NOT use import-time DEFAULT_UNIVERSE.
        # Long-lived serve_dashboard kept old pairs (ARB/ICP) and showed 0.00
        # for newly promoted seats (ADA/ZEC/STX) until process restart.
        try:
            universe = list(load_trading_basket() or []) or list(DEFAULT_UNIVERSE)
        except Exception:
            universe = list(DEFAULT_UNIVERSE)

    policy = _load_sentiment_policy()
    primary = str(policy.get("primary") or "x_with_free_fallback").strip().lower()
    free_fb = bool(policy.get("free_fallback_when_x_empty", True))
    min_posts = int(policy.get("x_min_usable_posts_total", 1) or 1)
    free_max_age = float(policy.get("free_max_age_hours", 18) or 18)
    do_age = bool(policy.get("apply_aging", True)) if apply_aging is None else bool(apply_aging)

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
            "aging_applied": False,
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

        # Reddit first when X unusable (complete clock); free only if Reddit empty
        if not x_info.get("usable"):
            rr_pre, rr_pre_meta = load_latest_reddit_scores(
                universe,
                max_age_hours=float(policy.get("reddit_bridge_max_age_hours", 8.0) or 8.0),
            )
            if rr_pre_meta.get("available") and int(rr_pre_meta.get("non_zero") or 0) > 0:
                filled_rr = 0
                for pair in universe:
                    rv = float(rr_pre.get(pair, 0.0) or 0.0)
                    if abs(out_scores[pair]["sentiment"]) <= 1e-9 and abs(rv) > 1e-9:
                        out_scores[pair] = {
                            "sentiment": rv,
                            "source": f"reddit:{rr_pre_meta.get('source') or 'reddit'}",
                        }
                        filled_rr += 1
                if filled_rr:
                    mode = "reddit_pre_bridge"
                    logger.info(
                        "X unusable — preloaded Reddit (%s) for %s pairs",
                        rr_pre_meta.get("source"),
                        filled_rr,
                    )

        # Free hybrid fallback when X unusable / still all zero AFTER Reddit try
        # (emergency only — free stays shadow for mid-cycle when X exists but aged)
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

    # --- Source-aware exponential aging (decision path default) ---
    aging_meta: Dict[str, Any] = {
        "applied": False,
        "x_half_life_minutes": float(policy.get("x_half_life_minutes", 15.0) or 15.0),
        "reddit_half_life_minutes": float(policy.get("reddit_half_life_minutes", 60.0) or 60.0),
        "free_half_life_minutes": float(policy.get("free_half_life_minutes", 60.0) or 60.0),
    }
    if do_age:
        aging_meta["applied"] = True
        for pair, info in out_scores.items():
            raw = float(info.get("sentiment", 0.0) or 0.0)
            src = str(info.get("source") or "none")
            if src == "none" or abs(raw) <= 1e-12:
                info["sentiment_raw"] = raw
                info["decay_factor"] = 1.0 if src == "none" else 0.0
                info["age_min"] = None
                info["half_life_min"] = None
                continue
            hl, stale_z = _half_life_for_source(src, policy)
            ts = _source_timestamp(pair, src, free_meta=free_meta, cache_path=cache_path)
            age_m = _age_minutes(ts)
            decay = _exponential_decay_factor(age_m, hl, stale_z)
            info["sentiment_raw"] = round(raw, 6)
            info["sentiment"] = round(raw * decay, 6)
            info["decay_factor"] = round(decay, 4)
            info["age_min"] = round(age_m, 1) if age_m is not None else None
            info["half_life_min"] = hl
            info["source_ts"] = ts
        sample_ages = [
            float(v.get("age_min"))
            for v in out_scores.values()
            if v.get("age_min") is not None
        ]
        sample_decays = [
            float(v.get("decay_factor"))
            for v in out_scores.values()
            if v.get("decay_factor") is not None
        ]
        med_age = sorted(sample_ages)[len(sample_ages) // 2] if sample_ages else None
        med_dec = sorted(sample_decays)[len(sample_decays) // 2] if sample_decays else None
        logger.info(
            "Sentiment aging ON mode=%s med_age_min=%s med_decay=%s "
            "x_hl=%sm reddit_hl=%sm",
            mode,
            med_age,
            med_dec,
            aging_meta["x_half_life_minutes"],
            aging_meta["reddit_half_life_minutes"],
        )

    # Complete clock: X aged-out / unavailable → latest Reddit (not free/Adanos)
    mode, bridge_meta = _apply_reddit_bridge(
        out_scores,
        universe=universe,
        policy=policy,
        x_info=x_info,
        do_age=do_age,
        mode=mode,
    )

    non_zero = sum(1 for v in out_scores.values() if abs(v["sentiment"]) > 1e-9)
    non_zero_raw = sum(
        1 for v in out_scores.values() if abs(float(v.get("sentiment_raw", v.get("sentiment", 0.0)) or 0.0)) > 1e-9
    )
    logger.info(
        f"Sentiment loaded for dynamic basket ({len(universe)} pairs). mode={mode} "
        f"non_zero={non_zero} non_zero_raw={non_zero_raw} aged={do_age} "
        f"x_posts={x_info.get('total_posts')}"
    )
    return {
        "scores": out_scores,
        "mode": mode,
        "policy": policy,
        "free_meta": free_meta,
        "x_usable": x_info,
        "non_zero": non_zero,
        "non_zero_raw": non_zero_raw,
        "aging_applied": do_age,
        "aging": aging_meta,
        "reddit_bridge": bridge_meta,
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
    return _age_minutes(get_sentiment_timestamp(cache_path))


def get_aged_sentiment_scores(
    universe: Optional[List[str]] = None,
    half_life_minutes: float = 15.0,
    cache_path: str = CANONICAL_CACHE,
    *,
    raw_scores: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Decision-path aged scores.

    Default path: canonical loader with source-aware aging (X 15m / Reddit 60m).
    If raw_scores is provided, apply a single uniform half_life (legacy helper).
    half_life_minutes default is 15 (X-shaped) — was 60, which overstated X relevance.
    """
    if raw_scores is not None:
        age = get_sentiment_freshness_minutes(cache_path) or 0.0
        if age <= 0:
            return {p: float(s) for p, s in raw_scores.items()}
        decay = 2 ** (-age / float(half_life_minutes or 15.0))
        aged = {p: round(float(s) * decay, 4) for p, s in raw_scores.items()}
        logger.info(
            f"Applied uniform sentiment aging on raw_scores: age={age}min, "
            f"half_life={half_life_minutes}min, decay_factor={decay:.3f}"
        )
        return aged

    # Canonical path already applies per-source HL; avoid double-aging.
    return load_sentiment_scores(universe=universe, cache_path=cache_path, apply_aging=True)


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
