#!/usr/bin/env python3
"""
One-shot FREE Reddit probe (public JSON API — no Apify, no paid X).

Compares Reddit text tier vs RSS (the intended replacement), plus free hybrid.

Writes:
  data/state/reddit_free_probe_cache.json
  data/state/rss_vs_reddit_correlation_latest.json
  reports/RSS_VS_REDDIT_PROBE_<date>.md (optional via --report)

Does NOT write live sentiment_cache.json or enable Apify.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase6.core.paths import (  # noqa: E402
    FREE_SENTIMENT_CACHE,
    PROJECT_ROOT,
    RSS_SENTIMENT_CACHE,
    load_trading_basket,
)

try:
    from textblob import TextBlob

    HAS_TB = True
except ImportError:
    HAS_TB = False

UA = "phase6-research-probe/1.0 (local; sentiment compare; contact: ops)"
OUT_REDDIT = PROJECT_ROOT / "data" / "state" / "reddit_free_probe_cache.json"
OUT_CORR = PROJECT_ROOT / "data" / "state" / "rss_vs_reddit_correlation_latest.json"
HISTORY = PROJECT_ROOT / "data" / "state" / "rss_vs_reddit_correlation_history.jsonl"
EPS = 1e-6
HALF_LIFE_H = 72.0
SLEEP_S = 1.35
TIMEOUT = 15

# Subreddits: general + majors (keep list short for rate limits)
SUBS_GENERAL = ["CryptoCurrency", "CryptoMarkets"]
SUBS_BY_PAIR = {
    "BTC-USD": ["Bitcoin"],
    "ETH-USD": ["ethereum"],
    "SOL-USD": ["solana"],
    "XRP-USD": ["Ripple"],
    "DOGE-USD": ["dogecoin"],
    "ADA-USD": ["cardano"],
    "AVAX-USD": ["Avax"],
    "LINK-USD": ["Chainlink"],
    "UNI-USD": ["UniSwap"],
    "ARB-USD": ["Arbitrum"],
    "OP-USD": ["optimism"],
}


def _rankdata(xs: List[float]) -> List[float]:
    n = len(xs)
    order = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 5:
        return None
    rx, ry = _rankdata(xs), _rankdata(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def load_keywords() -> Dict[str, List[str]]:
    path = PROJECT_ROOT / "config" / "sentiment_keywords.json"
    data = json.loads(path.read_text())
    pairs = data.get("pairs") or data
    out: Dict[str, List[str]] = {}
    for pair, cfg in pairs.items():
        if not isinstance(cfg, dict):
            continue
        terms: List[str] = []
        for t in cfg.get("reddit") or []:
            terms.append(str(t))
        base = pair.split("-")[0]
        terms.append(base)
        seen, clean = set(), []
        for t in terms:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                clean.append(t)
        out[pair] = clean
    return out


def polarity(text: str) -> float:
    if not HAS_TB or not text:
        return 0.0
    try:
        return float(TextBlob(text).sentiment.polarity)
    except Exception:
        return 0.0


def recency_w(created_utc: Optional[float], now_ts: float) -> float:
    if not created_utc:
        return 0.5
    age_h = max(0.0, (now_ts - float(created_utc)) / 3600.0)
    if age_h > HALF_LIFE_H * 2:
        return 0.0
    return float(0.5 ** (age_h / HALF_LIFE_H))


def reddit_get(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_search(sub: str, query: str, limit: int = 25) -> List[Dict[str, Any]]:
    q = urllib.parse.quote(query)
    url = (
        f"https://www.reddit.com/r/{sub}/search.json"
        f"?q={q}&restrict_sr=on&sort=new&t=week&limit={limit}"
    )
    try:
        data = reddit_get(url)
    except Exception as e:
        print(f"  fail r/{sub} q={query!r}: {e}")
        return []
    children = (data.get("data") or {}).get("children") or []
    return [c.get("data") or {} for c in children if isinstance(c, dict)]


def fetch_hot(sub: str, limit: int = 40) -> List[Dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
    try:
        data = reddit_get(url)
    except Exception as e:
        print(f"  fail hot r/{sub}: {e}")
        return []
    children = (data.get("data") or {}).get("children") or []
    return [c.get("data") or {} for c in children if isinstance(c, dict)]


def post_text(p: Dict[str, Any]) -> str:
    title = p.get("title") or ""
    body = p.get("selftext") or ""
    return f"{title}. {body}".strip()


def score_posts(posts: List[Dict[str, Any]], now_ts: float) -> Tuple[float, int, float]:
    obs: List[Tuple[float, float]] = []
    for p in posts:
        text = post_text(p)
        pol = polarity(text)
        if abs(pol) < 1e-9:
            continue
        w = recency_w(p.get("created_utc"), now_ts)
        # mild score weight from engagement
        ups = float(p.get("ups") or p.get("score") or 0)
        eng = 1.0 + min(2.0, math.log1p(max(0.0, ups)) / 5.0)
        w *= eng
        if w > 0:
            obs.append((pol, w))
    if not obs:
        return 0.0, 0, 0.0
    wsum = sum(w for _, w in obs)
    if wsum < 1e-12:
        return 0.0, len(obs), 0.0
    sent = sum(p * w for p, w in obs) / wsum
    conf = min(1.0, len(obs) / 15.0)
    sent = max(-1.0, min(1.0, sent * (0.35 + 0.65 * conf)))
    return round(sent, 4), len(obs), round(conf, 4)


def load_rss_scores() -> Dict[str, float]:
    if not RSS_SENTIMENT_CACHE.exists():
        return {}
    data = json.loads(RSS_SENTIMENT_CACHE.read_text())
    out = {}
    for p, e in data.items():
        if p in ("timestamp", "schema_version", "meta"):
            continue
        if isinstance(e, dict):
            out[p] = float(e.get("sentiment") or 0.0)
    return out


def load_free_hybrid() -> Dict[str, float]:
    if not FREE_SENTIMENT_CACHE.exists():
        return {}
    data = json.loads(FREE_SENTIMENT_CACHE.read_text())
    sent = data.get("sentiment") or {}
    out = {}
    for p, e in sent.items():
        if isinstance(e, dict):
            out[p] = float(e.get("sentiment_score") or 0.0)
        else:
            out[p] = float(e or 0.0)
    return out


def load_rss_text_only() -> Dict[str, float]:
    return load_rss_scores()


def corr_block(a: Dict[str, float], b: Dict[str, float], basket: List[str], label: str) -> Dict[str, Any]:
    pairs_detail = {}
    xs, ys = [], []
    sign_ok = 0
    sign_n = 0
    for p in basket:
        av, bv = a.get(p, 0.0), b.get(p, 0.0)
        sm = None
        if abs(av) > 0.02 and abs(bv) > 0.02:
            sm = (av > 0) == (bv > 0)
            sign_n += 1
            if sm:
                sign_ok += 1
        pairs_detail[p] = {"a": av, "b": bv, "sign_match": sm}
        xs.append(av)
        ys.append(bv)
    overlap = [p for p in basket if abs(a.get(p, 0)) > EPS and abs(b.get(p, 0)) > EPS]
    sp_all = spearman(xs, ys)
    if overlap:
        xo = [a[p] for p in overlap]
        yo = [b[p] for p in overlap]
        sp_ov = spearman(xo, yo) if len(overlap) >= 5 else None
    else:
        sp_ov = None
    return {
        "label": label,
        "n_a_nz": sum(1 for p in basket if abs(a.get(p, 0)) > EPS),
        "n_b_nz": sum(1 for p in basket if abs(b.get(p, 0)) > EPS),
        "n_overlap": len(overlap),
        "sign_agreement": (sign_ok / sign_n) if sign_n else None,
        "sign_n": sign_n,
        "spearman_all": None if sp_all is None else round(sp_all, 4),
        "spearman_overlap": None if sp_ov is None else round(sp_ov, 4),
        "pairs": pairs_detail,
    }


def pull_reddit(basket: List[str], kws: Dict[str, List[str]]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    # seed general hot posts once
    general_posts: List[Dict[str, Any]] = []
    for sub in SUBS_GENERAL:
        print(f"  hot r/{sub}...")
        general_posts.extend(fetch_hot(sub, limit=50))
        time.sleep(SLEEP_S)

    out: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "schema_version": 1,
        "meta": {
            "method": "reddit_public_json_textblob_72h",
            "half_life_hours": HALF_LIFE_H,
            "apify": False,
            "subs_general": SUBS_GENERAL,
            "note": "research probe only",
        },
    }
    api_calls = 0
    for pair in basket:
        terms = kws.get(pair) or [pair.split("-")[0]]
        primary = terms[0]
        posts: List[Dict[str, Any]] = []
        # pair-specific sub hot
        for sub in SUBS_BY_PAIR.get(pair) or []:
            print(f"  hot r/{sub} ({pair})...")
            posts.extend(fetch_hot(sub, limit=30))
            api_calls += 1
            time.sleep(SLEEP_S)
        # search in CryptoCurrency
        print(f"  search r/CryptoCurrency {primary!r}...")
        posts.extend(fetch_search("CryptoCurrency", primary, limit=25))
        api_calls += 1
        time.sleep(SLEEP_S)

        # filter general hot by keyword match
        low_terms = [t.lower() for t in terms]
        for gp in general_posts:
            text = post_text(gp).lower()
            if any(re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text) for t in low_terms):
                posts.append(gp)

        # dedupe by id
        seen = set()
        uniq = []
        for p in posts:
            pid = p.get("id") or p.get("name") or post_text(p)[:80]
            if pid in seen:
                continue
            seen.add(pid)
            uniq.append(p)

        sent, n, conf = score_posts(uniq, now_ts)
        out[pair] = {
            "sentiment": sent,
            "post_count": n,
            "confidence": conf,
            "raw_posts_fetched": len(uniq),
            "source": "reddit_public_json",
        }
        print(f"  {pair}: sent={sent:+.4f} scored_posts={n} fetched={len(uniq)}")

    out["meta"]["api_calls_approx"] = api_calls + len(SUBS_GENERAL)
    return out


def main() -> int:
    if not HAS_TB:
        print("ERROR: textblob required", file=sys.stderr)
        return 1
    basket = load_trading_basket()
    kws = load_keywords()
    print("=== FREE Reddit probe (no Apify) ===")
    reddit = pull_reddit(basket, kws)
    OUT_REDDIT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REDDIT.write_text(json.dumps(reddit, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_REDDIT}")

    r_scores = {
        p: float((reddit.get(p) or {}).get("sentiment") or 0.0)
        for p in basket
        if isinstance(reddit.get(p), dict)
    }
    rss = load_rss_text_only()
    free = load_free_hybrid()

    blocks = {
        "rss_vs_reddit": corr_block(rss, r_scores, basket, "RSS text vs Reddit free probe"),
        "free_hybrid_vs_reddit": corr_block(free, r_scores, basket, "Free hybrid vs Reddit free probe"),
    }
    # simple promote-ish gates for RSS as Reddit replacement
    b = blocks["rss_vs_reddit"]
    gates = {
        "overlap_ge_5": b["n_overlap"] >= 5,
        "sign_agreement_ge_0_55": (b["sign_agreement"] or 0) >= 0.55 if b["sign_n"] else False,
        "not_anti": (b["spearman_all"] is None) or (b["spearman_all"] > -0.2),
        "spearman_ge_0_25": (b["spearman_all"] is None) or (b["spearman_all"] >= 0.25),
        "reddit_coverage_ge_0_5": b["n_b_nz"] / max(1, len(basket)) >= 0.5,
        "rss_coverage_ge_0_5": b["n_a_nz"] / max(1, len(basket)) >= 0.5,
    }
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "basket": basket,
        "blocks": blocks,
        "gates_rss_as_reddit_proxy": gates,
        "rss_proxy_ready_snapshot": all(gates.values()),
        "paths": {
            "reddit_probe": str(OUT_REDDIT),
            "rss": str(RSS_SENTIMENT_CACHE),
            "free": str(FREE_SENTIMENT_CACHE),
        },
        "note": "SHADOW research — Apify off; public Reddit JSON only",
    }
    OUT_CORR.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    print(json.dumps({
        "rss_vs_reddit_sign": b.get("sign_agreement"),
        "rss_vs_reddit_spearman": b.get("spearman_all"),
        "overlap": b.get("n_overlap"),
        "proxy_ready": payload["rss_proxy_ready_snapshot"],
        "hybrid_sign": blocks["free_hybrid_vs_reddit"].get("sign_agreement"),
        "hybrid_spearman": blocks["free_hybrid_vs_reddit"].get("spearman_all"),
    }, indent=2))
    print(f"→ {OUT_CORR}")

    # markdown report
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = PROJECT_ROOT / "reports" / f"RSS_VS_REDDIT_PROBE_{day}.md"
    lines = [
        f"# RSS vs Reddit free probe — {day}",
        "",
        "**Apify:** off · **Reddit:** public JSON · **RSS:** expanded 72h basket",
        "",
        "## Headline metrics",
        "",
        f"| Compare | Sign agree | Spearman | Overlap nz |",
        f"|---------|------------|----------|------------|",
        f"| RSS vs Reddit | {b.get('sign_agreement')} (n={b.get('sign_n')}) | {b.get('spearman_all')} | {b.get('n_overlap')} |",
        f"| Free hybrid vs Reddit | {blocks['free_hybrid_vs_reddit'].get('sign_agreement')} | {blocks['free_hybrid_vs_reddit'].get('spearman_all')} | {blocks['free_hybrid_vs_reddit'].get('n_overlap')} |",
        "",
        f"**RSS-as-Reddit-proxy gates:** `{payload['rss_proxy_ready_snapshot']}` — {gates}",
        "",
        "## Per pair",
        "",
        "| Pair | Reddit | RSS | Free hybrid | Reddit posts scored |",
        "|------|--------|-----|-------------|---------------------|",
    ]
    for p in basket:
        rd = reddit.get(p) or {}
        lines.append(
            f"| {p} | {r_scores.get(p, 0):+.4f} | {rss.get(p, 0):+.4f} | {free.get(p, 0):+.4f} | {rd.get('post_count', 0)} |"
        )
    lines += [
        "",
        "## Read",
        "",
        "- This answers: can expanded RSS stand in for Reddit text?",
        "- X comparison is separate (`free_vs_x_correlation_*`).",
        "- Single snapshot — do not promote free fallback on one run.",
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
