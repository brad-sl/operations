#!/usr/bin/env python3
"""
Clean X (Twitter) sentiment fetcher for dynamic trading basket.

- Batched queries when basket > 5 pairs (improves per-pair post counts for statistical significance).
- Base sentiment calculation only (no transient buzz amplification on the sentiment value itself).
- Stores post_count + confidence (post-count scaling is the adequate weighting per requirements).
- Dynamic basket loaded from config/trading_config_phase6.json (opportunity_pool).
- Writes rich cache used by sentiment_scorer and opportunity scanner.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    TextBlob = None

# Canonical path per DATA_FLOW_AND_LOCATIONS.md + paths.py (no hardcodes, supports Hermes copies)
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from phase6.core.paths import PROJECT_ROOT, X_SENTIMENT_CACHE
    BASE_DIR = PROJECT_ROOT
    CACHE_FILE = X_SENTIMENT_CACHE
except Exception:
    # Fallback for direct runs
    BASE_DIR = Path("/home/brad/projects/crypto-trading-bot")
    CACHE_FILE = BASE_DIR / "data" / "state" / "x_sentiment_cache.json"

def load_bearer_token():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        print("❌ ERROR: .env file not found")
        return None
    token = None
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = [x.strip() for x in line.split('=', 1)]
                v = v.strip().strip('"\'')
                if k == "X_API_BEARER":
                    token = v
                    break
    except Exception as e:
        print(f"Error reading .env: {e}")
        return None
    return token if token else None

def fetch_x_posts_for_sentiment_analysis(
    bearer_token: str,
    keywords: List[str],
    max_results: int = 30,
    language: Optional[str] = "en"
) -> List[Dict[str, Any]]:
    if not keywords:
        return []
    query_parts = [f'"{kw}"' if " " in kw else kw for kw in keywords]
    query = " OR ".join(query_parts) + " -scam -is:retweet"
    if language:
        query += f" lang:{language}"
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,author_id,lang,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,verified"
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"⚠️ X API {resp.status_code}")
            return []
        data = resp.json()
        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {u["id"]: u for u in includes.get("users", [])}
        processed = []
        for t in tweets:
            processed.append({
                "text": t.get("text", ""),
                "public_metrics": t.get("public_metrics", {})
            })
        return processed
    except Exception as e:
        print(f"⚠️ X API error: {e}")
        return []

def distribute_posts_to_pairs(posts: List[Dict], keywords: Dict[str, str]) -> Dict[str, List[Dict]]:
    pair_posts = {pair: [] for pair in keywords}
    for post in posts:
        text = post.get("text", "").lower()
        for pair, kw in keywords.items():
            if kw.lower() in text:
                pair_posts[pair].append(post)
    return pair_posts

def calculate_sentiment(posts: List[Dict]) -> Dict[str, Any]:
    """Pure base sentiment. No buzz multiplier on the value (transient risk).
    post_count and confidence (volume scaling) are stored separately for scorer use.
    """
    post_count = len(posts)
    if post_count == 0:
        return {"sentiment": 0.0, "post_count": 0, "confidence": 0.0}

    total_eng = 0
    total_pol = 0.0
    pol_count = 0

    for p in posts:
        m = p.get("public_metrics", {})
        eng = m.get("like_count", 0) + m.get("retweet_count", 0)*1.5 + m.get("reply_count", 0)*0.5
        total_eng += eng
        if p.get("text") and TEXTBLOB_AVAILABLE:
            try:
                total_pol += TextBlob(p["text"]).sentiment.polarity
                pol_count += 1
            except:
                pass

    if total_eng == 0 and pol_count == 0:
        base = 0.0
    else:
        eng_c = (total_eng / post_count / 1000.0) if total_eng > 0 else 0.0
        pol_c = (total_pol / pol_count) if pol_count > 0 else 0.0
        if total_eng > 0 and pol_count > 0:
            base = 0.5 * eng_c + 0.5 * pol_c
        elif pol_count > 0:
            base = pol_c
        else:
            base = eng_c
        base = max(-1.0, min(1.0, base))

    # Volume-based confidence (scaling factor)
    conf = min(1.0, post_count / 25.0) if post_count >= 5 else max(0.05, post_count / 20.0)
    return {
        "sentiment": round(base, 4),
        "post_count": post_count,
        "confidence": round(conf, 3)
    }

def fetch_batched(pairs: List[str], kw_dict: Dict[str, str], bearer: str, batch_size: int = 6, max_res: int = 30) -> Dict[str, List[Dict]]:
    """Batched to ensure decent post counts per pair when basket is large."""
    agg = defaultdict(list)
    for i in range(0, len(pairs), batch_size):
        batch_pairs = pairs[i:i+batch_size]
        batch_kw = {p: kw_dict[p] for p in batch_pairs}
        print(f"  Batch {i//batch_size + 1}/{ (len(pairs)+batch_size-1)//batch_size }: {batch_pairs}")
        posts = fetch_x_posts_for_sentiment_analysis(bearer, list(batch_kw.values()), max_res)
        print(f"    → {len(posts)} posts for batch")
        dist = distribute_posts_to_pairs(posts, batch_kw)
        for p, lst in dist.items():
            agg[p].extend(lst)
    return dict(agg)

def main():
    # Dynamic from config (supports future basket management scripts)
    # Keywords are now loaded from the central source of truth.
    # See config/sentiment_keywords.json and phase6/core/sentiment_keywords.py
    # Updates are generated by scripts/optimize_sentiment_keywords.py
    try:
        from phase6.core.paths import load_trading_basket
        pairs = load_trading_basket()
    except Exception:
        # Fallback inline load (same logic)
        try:
            cfg = json.load(open("config/trading_config_phase6.json"))
            pairs = cfg.get("phase_6_specific", {}).get("opportunity_pool") or cfg.get("global_settings", {}).get("pairs", [])
            if not pairs:
                pairs = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD", "MATIC-USD"]
        except:
            pairs = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "UNI-USD", "ARB-USD", "OP-USD", "MATIC-USD"]

    # The defined method: pull from central loader
    from phase6.core.sentiment_keywords import get_x_keyword
    kw_dict = {p: get_x_keyword(p) for p in pairs}

    # Retain KEYWORD_MAP for any local code that still references it
    KEYWORD_MAP = {p: get_x_keyword(p) for p in pairs}

    bearer = load_bearer_token()
    if not bearer:
        print("❌ No X_API_BEARER")
        ts = datetime.utcnow().isoformat()
        cache = {p: {"sentiment": 0.0, "timestamp": ts, "post_count": 0, "confidence": 0.0} for p in pairs}
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(cache, open(CACHE_FILE, "w"), indent=2)
        return

    # === STALENESS GUARD + SMARTER BATCHING (cost control & sustainability) ===
    STALE_THRESHOLD_MINUTES = 25
    now = datetime.utcnow()
    stale_pairs = []
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                existing_cache = json.load(f)
            for p in pairs:
                entry = existing_cache.get(p, {})
                ts_str = entry.get("timestamp")
                if not ts_str:
                    stale_pairs.append(p)
                    continue
                try:
                    ts_clean = ts_str.replace("Z", "+00:00").rsplit("+", 1)[0]
                    ts = datetime.fromisoformat(ts_clean)
                    age_minutes = (now - ts).total_seconds() / 60.0
                    if age_minutes > STALE_THRESHOLD_MINUTES:
                        stale_pairs.append(p)
                except Exception:
                    stale_pairs.append(p)
        except Exception as e:
            print(f"  Cache check error: {e} — fetching all")
            stale_pairs = pairs[:]
    else:
        stale_pairs = pairs[:]

    if not stale_pairs:
        print(f"✅ X sentiment cache fresh for all {len(pairs)} pairs (<{STALE_THRESHOLD_MINUTES} min old). Skipping expensive API calls (cost guard).")
        return

    print(f"🔍 Fetching X for dynamic basket of {len(pairs)} pairs (stale needing refresh: {len(stale_pairs)})...")

    stale_kw = {p: kw_dict[p] for p in stale_pairs}

    # Smarter batching: larger batches to minimize number of /search/recent calls
    if len(stale_pairs) > 4:
        target_batches = max(1, min(3, (len(stale_pairs) + 5) // 6))
        batch_size = max(5, (len(stale_pairs) + target_batches - 1) // target_batches)
        batch_size = min(batch_size, 8)
        print(f"   Smarter batched mode (batch_size={batch_size}, target ~{target_batches} calls)")
        pair_posts = fetch_batched(stale_pairs, stale_kw, bearer, batch_size=batch_size, max_res=30)
    else:
        posts = fetch_x_posts_for_sentiment_analysis(bearer, list(stale_kw.values()), max_results=30)
        pair_posts = distribute_posts_to_pairs(posts, stale_kw)


    if len(pairs) > 5:
        print("   Batched mode enabled (better post counts per pair for significance)")
        pair_posts = fetch_batched(pairs, kw_dict, bearer, batch_size=6)
    else:
        posts = fetch_x_posts_for_sentiment_analysis(bearer, list(kw_dict.values()))
        pair_posts = distribute_posts_to_pairs(posts, kw_dict)

    details = {}
    for p in pairs:
        res = calculate_sentiment(pair_posts.get(p, []))
        details[p] = res
        print(f"  {p}: {res['sentiment']:+.4f} (posts={res['post_count']}, conf={res['confidence']})")

    ts = datetime.utcnow().isoformat()
    cache = {}
    for p in pairs:
        d = details[p]
        cache[p] = {
            "sentiment": d["sentiment"],
            "timestamp": ts,
            "post_count": d["post_count"],
            "confidence": d["confidence"]
        }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"✅ Cached {len(pairs)} pairs (base sentiment + volume metadata)")
    print(json.dumps({p: {"s": d["sentiment"], "posts": d["post_count"]} for p,d in details.items()}, indent=2))

if __name__ == "__main__":
    main()