#!/usr/bin/env python3
"""
Free sentiment hybrid merge (SHADOW only — does not write live sentiment_cache.json).

Order per FREE_SENTIMENT_OPTIONS:
  A_text = RSS (pair text)
  B_pos  = funding/OI (contrarian)
  If A: 0.65*A + 0.35*B
  Elif B: 0.8*B
  Else: F&G damped * pair_beta (Tier C empty-fill only)

Output: data/state/sentiment_cache_free.json (schema_version 3 compatible)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase6.core.paths import (  # noqa: E402
    FNG_CACHE,
    FREE_SENTIMENT_CACHE,
    FUNDING_SENTIMENT_CACHE,
    PROJECT_ROOT,
    RSS_SENTIMENT_CACHE,
    load_trading_basket,
)

PAIR_BETA = {
    "BTC-USD": 1.0,
    "ETH-USD": 1.0,
    "SOL-USD": 0.7,
    "XRP-USD": 0.7,
    "DOGE-USD": 0.5,
    "ADA-USD": 0.5,
    "AVAX-USD": 0.5,
    "LINK-USD": 0.6,
    "UNI-USD": 0.5,
    "ARB-USD": 0.4,
    "OP-USD": 0.4,
}


def _run(script: str) -> bool:
    path = PROJECT_ROOT / script
    print(f"  Running {script}...")
    try:
        cp = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if cp.stdout:
            print(cp.stdout.strip()[-500:])
        if cp.returncode != 0:
            print(f"    FAIL rc={cp.returncode} {(cp.stderr or '')[:300]}")
            return False
        return True
    except Exception as e:
        print(f"    EXC {e}")
        return False


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pair_sent(data: Dict[str, Any], pair: str) -> float:
    if pair not in data:
        return 0.0
    e = data[pair]
    if isinstance(e, dict):
        return float(e.get("sentiment", e.get("sentiment_score", 0.0)) or 0.0)
    try:
        return float(e)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    print(f"=== Free Sentiment Refresh (SHADOW) @ {datetime.now(timezone.utc).isoformat()} ===")
    ok_f = _run("fetch_fng_sentiment.py")
    ok_b = _run("fetch_funding_sentiment.py")
    ok_r = _run("fetch_rss_sentiment.py")

    basket = load_trading_basket()
    fng = _load(FNG_CACHE)
    funding = _load(FUNDING_SENTIMENT_CACHE)
    rss = _load(RSS_SENTIMENT_CACHE)

    fg_damped = float(fng.get("score_damped") or 0.0)

    sentiment: Dict[str, Dict[str, Any]] = {}
    sources_used = set()

    for pair in basket:
        a = _pair_sent(rss, pair)
        b = _pair_sent(funding, pair)
        components = {"text": round(a, 4), "funding": round(b, 4), "fng_damped": round(fg_damped, 4)}
        if abs(a) > 1e-6 and abs(b) > 1e-6:
            score = 0.65 * a + 0.35 * b
            src = "hybrid_rss_funding"
            sources_used.add("rss")
            sources_used.add("funding")
        elif abs(a) > 1e-6:
            score = a
            # mild funding tilt if present zero-ish skip
            src = "rss"
            sources_used.add("rss")
        elif abs(b) > 1e-6:
            score = 0.8 * b
            src = "funding"
            sources_used.add("funding")
        else:
            beta = PAIR_BETA.get(pair, 0.4)
            score = fg_damped * beta
            src = "fng" if abs(score) > 1e-6 else "none"
            if src == "fng":
                sources_used.add("fng")
        score = max(-1.0, min(1.0, float(score)))
        conf = 0.0
        if abs(a) > 1e-6 and abs(b) > 1e-6:
            conf = 0.7
        elif abs(a) > 1e-6:
            conf = 0.45
        elif abs(b) > 1e-6:
            conf = 0.5
        elif abs(score) > 1e-6:
            conf = 0.2
        sentiment[pair] = {
            "sentiment_score": round(score, 4),
            "source": src,
            "confidence": round(conf, 4),
            "components": components,
            "tier": "A" if "rss" in src else ("B" if "funding" in src else ("C" if src == "fng" else "Z")),
        }

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema_version": 3,
        "sentiment": sentiment,
        "meta": {
            "mode": "shadow_free_hybrid",
            "live_primary": False,
            "sources_ran": {"fng": ok_f, "funding": ok_b, "rss": ok_r},
            "sources_used": sorted(sources_used),
            "basket_size": len(basket),
            "fng_value": fng.get("value"),
            "fng_classification": fng.get("classification"),
            "note": "SHADOW only — runner still uses sentiment_cache.json / X path",
        },
    }
    FREE_SENTIMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FREE_SENTIMENT_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    nz = sum(1 for p in basket if abs(sentiment[p]["sentiment_score"]) > 1e-6)
    print(
        f"FREE CACHE written: {FREE_SENTIMENT_CACHE} non_zero={nz}/{len(basket)} "
        f"sources={sorted(sources_used)}"
    )
    return 0 if (ok_f or ok_b or ok_r) else 1


if __name__ == "__main__":
    raise SystemExit(main())
