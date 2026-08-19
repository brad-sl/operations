"""
Shared public crypto RSS helpers.

Used by:
  - fetch_rss_sentiment.py (scores only)
  - phase6/scripts/run_daily_dose.py (human daily dose cards)

No full article crawl. Soft-fail per feed. See docs/DATA_FLOW_AND_LOCATIONS.md.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

# Canonical working set (2026-07-29 probe). Dropped: dlnews 404, glassnode 403.
DEFAULT_FEEDS: Tuple[str, ...] = (
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://cryptoslate.com/feed/",
    "https://www.newsbtc.com/feed/",
    "https://bitcoinist.com/feed/",
    "https://u.today/rss",
    "https://blockworks.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
)

SOURCE_TIER: Dict[str, str] = {
    "cointelegraph.com": "A",
    "www.coindesk.com": "A",
    "coindesk.com": "A",
    "blockworks.co": "A",
    "bitcoinmagazine.com": "A",
    "decrypt.co": "B",
    "cryptoslate.com": "B",
    "www.newsbtc.com": "B",
    "newsbtc.com": "B",
    "bitcoinist.com": "B",
    "u.today": "B",
}

UA = "phase6-rss/1.2 (+local; sentiment+daily-dose)"
TIMEOUT = 20


@dataclass
class RssItem:
    title: str
    summary: str
    url: str
    source: str
    source_url: str
    published: Optional[datetime]
    feed_url: str

    @property
    def text(self) -> str:
        if self.summary:
            return f"{self.title}. {self.summary}".strip()
        return self.title


def strip_html(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def source_tier(host: str) -> str:
    if host in SOURCE_TIER:
        return SOURCE_TIER[host]
    # strip www.
    h = host[4:] if host.startswith("www.") else host
    return SOURCE_TIER.get(h, "C")


def parse_item_time(item: ET.Element, ns: Optional[Dict[str, str]] = None) -> Optional[datetime]:
    candidates: List[str] = []
    if ns:
        for tag in ("published", "updated"):
            t = item.findtext(f"a:{tag}", default="", namespaces=ns)
            if t:
                candidates.append(t)
    for tag in ("pubDate", "published", "updated", "{http://purl.org/dc/elements/1.1/}date"):
        t = item.findtext(tag) if "}" not in tag else item.findtext(tag)
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


def parse_feed_xml(body: bytes, feed_url: str) -> List[RssItem]:
    """Parse RSS/Atom bytes from known public feed URLs only (not user uploads).

    stdlib ElementTree is acceptable here: feeds are fixed allowlisted HTTPS
    endpoints we control in DEFAULT_FEEDS; we never resolve external entities
    from untrusted local files. Prefer defusedxml if added project-wide later.
    """
    items: List[RssItem] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    host = host_of(feed_url)
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title") or "")
        desc = strip_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        if not title:
            continue
        items.append(
            RssItem(
                title=title,
                summary=desc[:500],
                url=link or feed_url,
                source=host,
                source_url=feed_url,
                published=parse_item_time(item),
                feed_url=feed_url,
            )
        )
    if items:
        return items
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns):
        title = strip_html(entry.findtext("a:title", default="", namespaces=ns) or "")
        summary = strip_html(entry.findtext("a:summary", default="", namespaces=ns) or "")
        if not summary:
            summary = strip_html(entry.findtext("a:content", default="", namespaces=ns) or "")
        link_el = entry.find("a:link", ns)
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or "").strip()
        if not link:
            link = strip_html(entry.findtext("a:id", default="", namespaces=ns) or "")
        if not title:
            continue
        items.append(
            RssItem(
                title=title,
                summary=summary[:500],
                url=link or feed_url,
                source=host,
                source_url=feed_url,
                published=parse_item_time(entry, ns=ns),
                feed_url=feed_url,
            )
        )
    return items


def fetch_feed(url: str, timeout: int = TIMEOUT, ua: str = UA) -> List[RssItem]:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except Exception as e:
        print(f"  RSS fail {url}: {e}")
        return []
    return parse_feed_xml(body, url)


def fetch_all_feeds(
    feeds: Optional[Sequence[str]] = None,
    timeout: int = TIMEOUT,
) -> Tuple[List[RssItem], List[Dict]]:
    """Return (items, feed_stats)."""
    urls = list(feeds) if feeds is not None else list(DEFAULT_FEEDS)
    all_items: List[RssItem] = []
    stats: List[Dict] = []
    for url in urls:
        got = fetch_feed(url, timeout=timeout)
        stats.append({"url": url, "n": len(got), "ok": len(got) > 0})
        print(f"  feed {host_of(url) or url}: {len(got)} items")
        all_items.extend(got)
    return all_items, stats


def load_pair_keywords(project_root) -> Dict[str, List[str]]:
    import json
    from pathlib import Path

    path = Path(project_root) / "config" / "sentiment_keywords.json"
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
        # common long names
        if base.upper() == "BTC":
            terms.extend(["bitcoin", "btc"])
        if base.upper() == "ETH":
            terms.extend(["ethereum", "ether", "eth"])
        seen = set()
        clean = []
        for t in terms:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                clean.append(t)
        out[pair] = clean
    return out
