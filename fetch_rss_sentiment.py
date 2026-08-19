#!/usr/bin/env python3
"""
Free RSS headline sentiment → data/state/rss_sentiment_cache.json

Longer-horizon text tier (Reddit stand-in for free hybrid):
  - Wider public crypto RSS basket
  - 72h recency half-life on headline polarity
  - Pair map via config/sentiment_keywords.json
  - Zeros when no pair mentions — never invent

SHADOW path only via refresh_sentiment_free.py (does not write live sentiment_cache).
"""
from __future__ import annotations

import json
import math
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase6.core.paths import PROJECT_ROOT, RSS_SENTIMENT_CACHE, load_trading_basket

try:
    from textblob import TextBlob

    HAS_TB = True
except ImportError:
    HAS_TB = False

UA = "phase6-free-sentiment/1.1 (+local research; rss longer-horizon)"
# Expanded basket — public feeds only; failures are soft-skip
FEEDS = [
    # Tier A — core news (existing + expand)
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://cryptoslate.com/feed/",
    "https://www.newsbtc.com/feed/",
    "https://bitcoinist.com/feed/",
    "https://u.today/rss",
    # Tier B — research / markets narrative
    "https://blockworks.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]
# Dropped after live probe 2026-07-29: dlnews 404, glassnode 403.
# Optional later: theblock.co/rss.xml, messari.io/rss (often flaky).

HALF_LIFE_HOURS = 72.0
MIN_HITS = 1
TIMEOUT = 20
MAX_AGE_HOURS = 72.0 * 2  # drop items older than 2 half-lives


def _strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_item_time(item: ET.Element, ns: Optional[Dict[str, str]] = None) -> Optional[datetime]:
    """Best-effort pub date → aware UTC."""
    candidates = []
    if ns:
        for tag in ("published", "updated"):
            t = item.findtext(f"a:{tag}", default="", namespaces=ns)
            if t:
                candidates.append(t)
    for tag in ("pubDate", "published", "updated", "{http://purl.org/dc/elements/1.1/}date"):
        t = item.findtext(tag) if "}" not in tag else item.findtext(tag)
        # also try with dc namespace children
        if not t:
            for child in item:
                if child.tag.endswith("date") or child.tag.endswith("pubDate"):
                    t = child.text
                    break
        if t:
            candidates.append(t)
    for raw in candidates:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def load_keywords() -> Dict[str, List[str]]:
    path = PROJECT_ROOT / "config" / "sentiment_keywords.json"
    data = json.loads(path.read_text())
    pairs = data.get("pairs") or data
    out: Dict[str, List[str]] = {}
    for pair, cfg in pairs.items():
        if not isinstance(cfg, dict):
            continue
        terms: List[str] = []
        x = cfg.get("x")
        if x:
            terms.append(str(x))
        for t in cfg.get("reddit") or []:
            terms.append(str(t))
        base = pair.split("-")[0]
        terms.append(base)
        seen = set()
        clean = []
        for t in terms:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                clean.append(t)
        out[pair] = clean
    return out


def fetch_feed(url: str) -> List[Tuple[str, str, Optional[datetime]]]:
    """Return list of (title, text, published_utc|None)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
    except Exception as e:
        print(f"  RSS fail {url}: {e}")
        return []
    items: List[Tuple[str, str, Optional[datetime]]] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"  RSS parse fail {url}: {e}")
        return []
    # RSS 2.0
    for item in root.findall(".//item"):
        title = _strip_html((item.findtext("title") or ""))
        desc = _strip_html((item.findtext("description") or ""))
        text = f"{title}. {desc}".strip()
        ts = _parse_item_time(item)
        if text:
            items.append((title, text, ts))
    # Atom
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns):
            title = _strip_html(entry.findtext("a:title", default="", namespaces=ns) or "")
            summary = _strip_html(
                entry.findtext("a:summary", default="", namespaces=ns) or ""
            )
            if not summary:
                summary = _strip_html(
                    entry.findtext("a:content", default="", namespaces=ns) or ""
                )
            text = f"{title}. {summary}".strip()
            ts = _parse_item_time(entry, ns=ns)
            if text:
                items.append((title, text, ts))
    return items


def polarity(text: str) -> float:
    if not HAS_TB:
        return 0.0
    try:
        return float(TextBlob(text).sentiment.polarity)
    except Exception:
        return 0.0


def recency_weight(published: Optional[datetime], now: datetime) -> float:
    """Exponential decay; missing date → mild mid weight (0.5)."""
    if published is None:
        return 0.5
    age_h = max(0.0, (now - published).total_seconds() / 3600.0)
    if age_h > MAX_AGE_HOURS:
        return 0.0
    # half-life: w = 0.5 ** (age / half_life)
    return float(0.5 ** (age_h / HALF_LIFE_HOURS))


def main() -> int:
    if not HAS_TB:
        print("ERROR: textblob required", file=sys.stderr)
        return 1
    basket = load_trading_basket()
    kws = load_keywords()
    now = datetime.now(timezone.utc)
    headlines: List[Tuple[str, str, Optional[datetime]]] = []
    feed_stats: List[Dict[str, Any]] = []
    for url in FEEDS:
        got = fetch_feed(url)
        print(f"  feed {url}: {len(got)} items")
        feed_stats.append({"url": url, "n": len(got)})
        headlines.extend(got)

    # pair → list of (polarity, weight)
    pair_obs: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    pair_hits: Dict[str, int] = defaultdict(int)
    dropped_old = 0

    for _title, text, pub in headlines:
        w = recency_weight(pub, now)
        if w <= 0:
            dropped_old += 1
            continue
        low = text.lower()
        pol = polarity(text)
        if abs(pol) < 1e-9:
            continue
        for pair in basket:
            terms = kws.get(pair) or [pair.split("-")[0]]
            hit = False
            for t in terms:
                if re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", low):
                    hit = True
                    break
            if hit:
                pair_obs[pair].append((pol, w))
                pair_hits[pair] += 1

    out: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "schema_version": 2,
        "meta": {
            "feeds": FEEDS,
            "feed_stats": feed_stats,
            "headlines": len(headlines),
            "dropped_older_than_max_age": dropped_old,
            "method": "textblob_recency_weighted",
            "half_life_hours": HALF_LIFE_HOURS,
            "max_age_hours": MAX_AGE_HOURS,
            "min_hits": MIN_HITS,
        },
    }
    for pair in basket:
        obs = pair_obs.get(pair) or []
        hits = pair_hits.get(pair) or 0
        if hits < MIN_HITS or not obs:
            sent = 0.0
            conf = 0.0
            wsum = 0.0
        else:
            wsum = sum(w for _, w in obs)
            if wsum < 1e-12:
                sent = 0.0
                conf = 0.0
            else:
                sent = sum(p * w for p, w in obs) / wsum
                # confidence: hit count + effective weight mass
                conf = min(1.0, (hits / 8.0) * 0.5 + min(1.0, wsum / 3.0) * 0.5)
                sent = sent * (0.35 + 0.65 * conf)
                sent = max(-1.0, min(1.0, sent))
        out[pair] = {
            "sentiment": round(sent, 4),
            "post_count": hits,
            "confidence": round(conf if hits else 0.0, 4),
            "weight_sum": round(wsum if hits else 0.0, 4),
            "source": "rss",
            "half_life_hours": HALF_LIFE_HOURS,
        }

    RSS_SENTIMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RSS_SENTIMENT_CACHE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    nz = sum(1 for p in basket if abs(out[p]["sentiment"]) > 1e-6)
    feeds_ok = sum(1 for f in feed_stats if f["n"] > 0)
    print(
        f"RSS OK headlines={len(headlines)} feeds_ok={feeds_ok}/{len(FEEDS)} "
        f"non_zero_pairs={nz} half_life_h={HALF_LIFE_HOURS} → {RSS_SENTIMENT_CACHE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
