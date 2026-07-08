#!/usr/bin/env python3
# See docs/DATA_FLOW_AND_LOCATIONS.md + phase6/core/paths.py
"""
Phase 6 - Sentiment Refresh Orchestrator (every 30 min + staleness guard in fetcher)

Properly structured version:
- Calls the stable root-level fetch scripts via subprocess
- Merges results into the canonical cache used by phase6/core/sentiment_scorer.py (data/state/sentiment_cache.json)
- Also persists real (X/Reddit) scores to DB sentiment_scores (with posts counts where available) for shared queries and reddit gate.
- Full 11-pair basket coverage, prefer X, no clobber of good scores.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Canonical import per DATA_FLOW_AND_LOCATIONS.md + paths.py (no hardcodes)
# Works whether run from project root, phase6/scripts/, or Hermes profile copy
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from phase6.core.paths import PROJECT_ROOT, load_project_dotenv, REDDIT_SENTIMENT_CACHE

load_project_dotenv()

CANONICAL_CACHE = PROJECT_ROOT / "data" / "state" / "sentiment_cache.json"
CANONICAL_CACHE.parent.mkdir(parents=True, exist_ok=True)

X_FETCH = PROJECT_ROOT / "fetch_x_sentiment.py"
REDDIT_FETCH = PROJECT_ROOT / "fetch_reddit_sentiment.py"

X_CACHE = PROJECT_ROOT / "data" / "state" / "x_sentiment_cache.json"
REDDIT_CACHE = REDDIT_SENTIMENT_CACHE


def run_fetcher(script_path: Path, name: str) -> bool:
    """Run a fetch script and return success status."""
    print(f"  Running {name}...")
    try:
        # Use the canonical wrapper to apply NumPy workarounds
        env = os.environ.copy()
        env["OPENBLAS_CORETYPE"] = "GENERIC"
        cmd =  [str(PROJECT_ROOT / "run_sentiment.sh"), str(script_path)]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180
        )
        if result.returncode == 0:
            print(f"    {name} completed successfully")
            return True
        else:
            print(f"    {name} failed (exit {result.returncode})")
            if result.stderr:
                print(f"    stderr: {result.stderr.strip()[:300]}")
            return False
    except Exception as e:
        print(f"    {name} exception: {e}")
        return False


def merge_into_canonical():
    """Merge X + Reddit caches into the format expected by sentiment_scorer.py.
    
    P2-01 cleanup:
    - Always cover full dynamic basket (11+ pairs)
    - Prefer X (real primary signal) over Reddit; only use Reddit when X==0 or absent (mirrors scorer logic)
    - Do NOT clobber good X scores with 0s from Reddit
    - Fill missing pairs as 0 (no phantom omission)
    - Write schema_version for scorer fallback compatibility
    - Track source cleanly: x | reddit | x+reddit (when both contributed non-zero)
    """
    from phase6.core.paths import load_trading_basket  # ensure canonical basket

    basket = load_trading_basket()
    now_ts = datetime.now(timezone.utc).isoformat()

    unified = {
        "timestamp": now_ts,
        "schema_version": 3,
        "sentiment": {},
        "meta": {
            "source": "refresh_sentiment.py (P2-01 fixed)",
            "x_cache": str(X_CACHE),
            "reddit_cache": str(REDDIT_CACHE),
            "basket_size": len(basket)
        }
    }

    # init all to 0 to guarantee coverage
    for pair in basket:
        unified["sentiment"][pair] = {"sentiment_score": 0.0, "source": "none"}

    x_contrib = {}
    # Load X sentiment (prefer this)
    if X_CACHE.exists():
        try:
            with open(X_CACHE) as f:
                x_data = json.load(f)
            sentiments = x_data.get("sentiments", x_data)
            if "data" in sentiments and isinstance(sentiments.get("data"), dict):
                sentiments = sentiments["data"]
            for pair, entry in list(sentiments.items()):
                if not isinstance(pair, str) or "-" not in pair or pair in ("timestamp", "schema_version", "meta", "data"):
                    continue
                if isinstance(entry, dict):
                    raw_score = entry.get("sentiment_score", entry.get("score", entry.get("sentiment", 0.0)))
                    try:
                        score = float(raw_score)
                    except (ValueError, TypeError):
                        score = 0.0
                else:
                    try:
                        score = float(entry) if entry else 0.0
                    except (ValueError, TypeError):
                        score = 0.0
                if pair in unified["sentiment"]:
                    unified["sentiment"][pair]["sentiment_score"] = score
                    unified["sentiment"][pair]["source"] = "x"
                    x_contrib[pair] = score
        except Exception as e:
            print(f"  Warning: failed to read X cache: {e}")

    reddit_contrib = {}
    # Load Reddit sentiment (only if no good X or X==0)
    if REDDIT_CACHE.exists():
        try:
            with open(REDDIT_CACHE) as f:
                reddit_data = json.load(f)
            sentiments = reddit_data.get("sentiments", reddit_data)
            for pair, entry in list(sentiments.items()):
                if not isinstance(pair, str) or "-" not in pair or pair in ("timestamp", "schema_version", "meta", "data"):
                    continue
                if isinstance(entry, dict):
                    raw_score = entry.get("sentiment_score", entry.get("score", entry.get("sentiment", 0.0)))
                    try:
                        score = float(raw_score)
                    except (ValueError, TypeError):
                        score = 0.0
                else:
                    try:
                        score = float(entry) if entry else 0.0
                    except (ValueError, TypeError):
                        score = 0.0
                if pair in unified["sentiment"]:
                    cur = unified["sentiment"][pair].get("sentiment_score", 0.0)
                    if cur == 0.0 and score != 0.0:
                        unified["sentiment"][pair]["sentiment_score"] = score
                        unified["sentiment"][pair]["source"] = "reddit"
                        reddit_contrib[pair] = score
                    elif cur != 0.0 and score != 0.0:
                        # both real: keep X (primary), mark merged
                        unified["sentiment"][pair]["source"] = "x+reddit"
                        reddit_contrib[pair] = score  # note only
        except Exception as e:
            print(f"  Warning: failed to read Reddit cache: {e}")

    # Write canonical cache
    with open(CANONICAL_CACHE, "w") as f:
        json.dump(unified, f, indent=2)

    non_zero = sum(1 for v in unified["sentiment"].values() if v.get("sentiment_score", 0) != 0)
    print(f"  Canonical cache updated: {CANONICAL_CACHE} ({len(unified['sentiment'])} pairs, non-zero: {non_zero})")
    if x_contrib:
        print(f"    X contributed to {len(x_contrib)}")
    if reddit_contrib:
        print(f"    Reddit contributed to {len(reddit_contrib)} (non-clobbered)")

    return unified



def persist_to_db(unified: dict, x_cache_path: Path = None, reddit_cache_path: Path = None):
    """Persist the merged real sentiment scores to DB with posts/source for scorer _load_reddit and dashboard.
    Uses post_count from x cache where possible; for reddit sets posts=1 when contributed (since fetch aggregates).
    """
    import sqlite3
    from datetime import datetime
    try:
        db_path = PROJECT_ROOT / "data" / "phase6.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_scores (ts TEXT NOT NULL, pair TEXT NOT NULL, score REAL, posts INTEGER DEFAULT 0, source TEXT, confidence REAL, status TEXT, PRIMARY KEY (ts, pair))
        """)
        ts = datetime.utcnow().isoformat() + "Z"
        sent_block = unified.get("sentiment", {})
        x_data = {}
        if x_cache_path and x_cache_path.exists():
            try:
                with open(x_cache_path) as f: x_data = json.load(f)
            except: pass
        rows = []
        for pair, entry in sent_block.items():
            score = float(entry.get("sentiment_score", 0.0))
            src = entry.get("source", "merged")
            posts = 0
            conf = None
            if src == "x" or src == "x+reddit":
                ex = x_data.get(pair, {}) if isinstance(x_data, dict) else {}
                posts = int(ex.get("post_count", ex.get("posts", 0))) if isinstance(ex, dict) else 0
                conf = float(ex.get("confidence", 0.3)) if isinstance(ex, dict) else 0.3
            elif src == "reddit":
                posts = 1  # aggregate, at least one "result"
                conf = 0.4
            rows.append((ts, pair, score, posts, src, conf, "refreshed"))
        if rows:
            cur.executemany(
                "INSERT OR REPLACE INTO sentiment_scores (ts, pair, score, posts, source, confidence, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows
            )
            conn.commit()
            print(f"  DB sentiment_scores updated for {len(rows)} pairs (real sources, posts where avail)")
        conn.close()
    except Exception as e:
        print(f"  [WARN] DB persist for sentiment skipped: {e}")


def main():
    print(f"=== Sentiment Refresh @ {datetime.now(timezone.utc).isoformat()} ===")

    x_ok = run_fetcher(X_FETCH, "X/Twitter sentiment")
    reddit_ok = run_fetcher(REDDIT_FETCH, "Reddit sentiment")

    if x_ok or reddit_ok:
        try:
            unified = merge_into_canonical() or {}
            # P2-01: persist real to DB too (for reddit gate + dashboard consistency)
            try:
                persist_to_db(unified, X_CACHE, REDDIT_CACHE)
            except Exception as pe:
                print(f"  persist_to_db warning: {pe}")
        except Exception as e:
            print(f"  Merge failed: {e}")
    else:
        print("  No fetchers succeeded — skipping merge")

    print("=== Refresh complete ===")


if __name__ == "__main__":
    main()