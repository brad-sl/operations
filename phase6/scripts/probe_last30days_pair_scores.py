#!/usr/bin/env python3
"""
last30days → crude pair-score probe (RESEARCH shape only).

Maps findings in ~/.local/share/last30days/research.db onto the Phase 6 basket
via sentiment_keywords + TextBlob polarity × engagement. Output is a
**research artifact**, not a live sentiment candidate.

Role vs Adanos/RSS/free:
  - last30days = multi-source narrative briefs (Reddit/X/HN/…) ranked by engagement
  - Wrong product shape for deploy gates (no calibrated pair schema, slow, LLM cost)
  - Useful for: "does chatter direction roughly agree with X/RSS this week?" digs

Writes: data/state/last30days_pair_score_probe_latest.json
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase6.core.paths import LAST30_PAIR_PROBE, PROJECT_ROOT, load_trading_basket  # noqa: E402
from phase6.core.simple_polarity import try_textblob_polarity  # noqa: E402

DB = Path.home() / ".local" / "share" / "last30days" / "research.db"
KW = PROJECT_ROOT / "config" / "sentiment_keywords.json"
HAS_TB = False
try:
    from textblob import TextBlob  # noqa: F401

    HAS_TB = True
except Exception:
    HAS_TB = False


def _keywords_for_pair(pair: str, kw_doc: Dict[str, Any]) -> List[str]:
    pairs = (kw_doc or {}).get("pairs") or {}
    entry = pairs.get(pair) or {}
    out: List[str] = []
    for k in ("x", "reddit"):
        v = entry.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.extend(str(x) for x in v)
    for k in ("x_supplemental",):
        v = entry.get(k) or []
        if isinstance(v, list):
            out.extend(str(x) for x in v)
    # base ticker
    out.append(pair.split("-")[0])
    # unique lower
    seen = set()
    clean = []
    for t in out:
        t2 = t.strip().lstrip("$")
        if not t2:
            continue
        low = t2.lower()
        if low not in seen:
            seen.add(low)
            clean.append(t2)
    return clean


def _polarity(text: str) -> float:
    return try_textblob_polarity(text or "")


def main() -> int:
    basket = load_trading_basket()
    kw_doc = json.loads(KW.read_text(encoding="utf-8")) if KW.exists() else {}
    pair_kws = {p: _keywords_for_pair(p, kw_doc) for p in basket}

    if not DB.exists():
        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "no_db",
            "path": str(DB),
            "note": "last30days research.db missing — run last30 research first",
            "role": "research_only_not_deploy",
        }
        LAST30_PAIR_PROBE.parent.mkdir(parents=True, exist_ok=True)
        LAST30_PAIR_PROBE.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("NO_DB", DB)
        return 2

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, source, source_title, content, summary, engagement_score, relevance_score, first_seen
        FROM findings
        WHERE COALESCE(dismissed, 0) = 0
        ORDER BY engagement_score DESC
        LIMIT 500
        """
    ).fetchall()

    # accumulators: weighted polarity sum / weight
    num: Dict[str, float] = defaultdict(float)
    den: Dict[str, float] = defaultdict(float)
    hits: Dict[str, int] = defaultdict(int)
    sources_hit: Dict[str, set] = defaultdict(set)

    for r in rows:
        title = (r["source_title"] or "") or ""
        body = (r["content"] or r["summary"] or "") or ""
        text = f"{title}\n{body}"
        text_l = text.lower()
        eng = float(r["engagement_score"] or 0.0)
        rel = float(r["relevance_score"] or 0.0)
        w = max(0.1, math.log1p(max(0.0, eng)) + 0.5 * max(0.0, rel))
        pol = _polarity(text)
        src = r["source"] or "unknown"
        for pair, kws in pair_kws.items():
            matched = False
            for kw in kws:
                # word-ish match
                if re.search(rf"(?<![a-z0-9]){re.escape(kw.lower())}(?![a-z0-9])", text_l):
                    matched = True
                    break
            if not matched:
                continue
            num[pair] += pol * w
            den[pair] += w
            hits[pair] += 1
            sources_hit[pair].add(str(src))

    sentiment: Dict[str, Dict[str, Any]] = {}
    for pair in basket:
        if den[pair] <= 0 or hits[pair] <= 0:
            continue
        score = max(-1.0, min(1.0, num[pair] / den[pair]))
        sentiment[pair] = {
            "sentiment_score": round(score, 4),
            "source": "last30days_probe",
            "hits": hits[pair],
            "weight_sum": round(den[pair], 3),
            "sources": sorted(sources_hit[pair]),
            "confidence": round(min(0.7, 0.2 + 0.05 * hits[pair]), 3),
        }

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if sentiment else "empty",
        "schema_version": 3,
        "role": "research_only_not_deploy",
        "db": str(DB),
        "n_findings_scanned": len(rows),
        "has_textblob": HAS_TB,
        "sentiment": sentiment,
        "meta": {
            "live_primary": False,
            "boundary": "last30days = research ≠ deploy",
            "vs_adanos": "Adanos = calibrated Reddit pair scores; last30 = engagement-ranked multi-source narrative",
            "vs_rss": "RSS = free continuous headlines; last30 = episodic research runs",
            "potential_role": [
                "weekly operator brief / regime color",
                "offline dig: does narrative agree with X/Adanos sign?",
                "NOT mid-cycle gate input without multi-day pair-score bakeoff + Brad GO",
            ],
            "n_pairs_scored": len(sentiment),
            "basket_size": len(basket),
        },
    }
    LAST30_PAIR_PROBE.parent.mkdir(parents=True, exist_ok=True)
    LAST30_PAIR_PROBE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"last30 probe pairs={len(sentiment)}/{len(basket)} findings={len(rows)} "
        f"tb={HAS_TB} → {LAST30_PAIR_PROBE}"
    )
    for p, e in list(sentiment.items())[:8]:
        print(f"  {p}: {e['sentiment_score']:+.3f} hits={e['hits']} src={e['sources']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
