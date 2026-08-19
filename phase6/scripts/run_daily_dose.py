#!/usr/bin/env python3
"""
Daily Dose Phase A — rank public RSS into human-readable top-N cards.

Writes:
  data/state/daily_dose_latest.json
  data/state/daily_dose_history.jsonl  (append one run summary)
  data/state/daily_dose_telegram_preview.txt

NOT a trading signal. Does not write sentiment_cache or touch allocator.
Spec: docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.paths import (  # noqa: E402
    DAILY_DOSE_HISTORY,
    DAILY_DOSE_LATEST,
    DAILY_DOSE_TELEGRAM_PREVIEW,
    PROJECT_ROOT,
    load_trading_basket,
)
from phase6.core.rss_feeds import (  # noqa: E402
    DEFAULT_FEEDS,
    RssItem,
    fetch_all_feeds,
    load_pair_keywords,
    source_tier,
    strip_html,
)
from phase6.core.daily_dose_editorial import (  # noqa: E402
    apply_basket_pair_diversity,
    editorial_pass,
    format_tickers_display,
    md_source_link,
)

SCHEMA_VERSION = 2
METHOD = "rss_rank_v1+editorial_v1"

# Frozen weights (spec §4.3)
W_RELEVANCE = 0.35
W_SOURCE = 0.15
W_EVENT = 0.25
W_RECENCY = 0.15
W_NOVELTY = 0.10

EVENT_PATTERNS = [
    (r"\betf\b", "etf"),
    (r"\bsec\b", "sec"),
    (r"regulat", "regulation"),
    (r"\bhack", "hack"),
    (r"exploit", "exploit"),
    (r"liquidat", "liquidation"),
    (r"bankrupt", "bankruptcy"),
    (r"\brate cut\b|\bfomc\b|\bfed\b", "macro_rates"),
    (r"approv", "approval"),
    (r"lawsuit|sued|indict", "legal"),
    (r"outage|halted|halt\b", "outage"),
    (r"depeg", "depeg"),
    (r"unlock", "unlock"),
    (r"\blisting\b|lists\b", "listing"),
    (r"blackrock|fidelity|grayscale", "institution"),
    (r"strategy\b|microstrategy|mstr\b", "treasury_co"),
]

TIER_SCORE = {"A": 1.0, "B": 0.7, "C": 0.4}
RECENCY_HALF_LIFE_H = 18.0
DEFAULT_WINDOW_H = 36.0
DEFAULT_TOP_N = 8
COMPOSITE_FLOOR = 0.15
JACCARD_DUP = 0.55


def _norm_title(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokens(t: str) -> Set[str]:
    stop = {
        "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
        "after", "as", "at", "by", "from", "is", "are", "be", "this", "that",
        "its", "it", "into", "over", "under", "new", "says", "report", "crypto",
    }
    return {w for w in _norm_title(t).split() if len(w) > 2 and w not in stop}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def item_id(title: str, source: str, day: str) -> str:
    raw = f"{_norm_title(title)}|{source}|{day}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def match_tickers(text: str, kws: Dict[str, List[str]], basket: Sequence[str]) -> List[str]:
    low = text.lower()
    hits = []
    for pair in basket:
        terms = kws.get(pair) or [pair.split("-")[0]]
        for t in terms:
            if re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", low):
                hits.append(pair)
                break
    return hits


def match_events(text: str) -> List[str]:
    low = text.lower()
    tags = []
    for pat, tag in EVENT_PATTERNS:
        if re.search(pat, low, flags=re.I):
            tags.append(tag)
    return tags


def recency_score(published: Optional[datetime], now: datetime, window_h: float) -> float:
    if published is None:
        return 0.45
    age_h = (now - published).total_seconds() / 3600.0
    if age_h < 0:
        age_h = 0.0
    if age_h > window_h:
        return 0.0
    return float(0.5 ** (age_h / RECENCY_HALF_LIFE_H))


def rank_items(
    raw: List[RssItem],
    basket: Sequence[str],
    kws: Dict[str, List[str]],
    now: datetime,
    window_h: float,
    top_n: int,
    open_positions: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    open_positions = open_positions or set()
    candidates: List[Dict[str, Any]] = []

    for it in raw:
        if it.published is not None:
            age_h = (now - it.published).total_seconds() / 3600.0
            if age_h > window_h:
                continue
        text = it.text
        tickers = match_tickers(text, kws, basket)
        # BTC macro floor: bitcoin in title counts even if pair map missed
        if not tickers and re.search(r"\bbitcoin\b|\bbtc\b", it.title, re.I):
            if "BTC-USD" in basket:
                tickers = ["BTC-USD"]
        events = match_events(text)
        tier = source_tier(it.source)
        rel = 0.0
        why = []
        if tickers:
            rel = 1.0
            why.append("basket:" + ",".join(tickers[:3]))
            if open_positions and set(tickers) & open_positions:
                rel = min(1.0, rel + 0.5)
                why.append("open_pos")
        elif events:
            # macro/event without ticker — mild relevance
            rel = 0.35
            why.append("event_only")
        src_s = TIER_SCORE.get(tier, 0.4)
        why.append(f"tier:{tier}")
        ev_s = min(1.0, 0.4 * len(events) + (0.2 if events else 0.0))
        if events:
            why.append("event:" + ",".join(events[:3]))
        rec_s = recency_score(it.published, now, window_h)
        if rec_s <= 0:
            continue

        day = (it.published or now).strftime("%Y-%m-%d")
        card = {
            "id": item_id(it.title, it.source, day),
            "ts_published": it.published.isoformat() if it.published else None,
            "ts_seen": now.isoformat(),
            "source": it.source,
            "source_url": it.source_url,
            "title": it.title,
            "summary": (it.summary or "")[:240],
            "url": it.url,
            "tickers": tickers,
            "event_tags": events,
            "scores": {
                "relevance": round(rel, 4),
                "source_tier": round(src_s, 4),
                "event": round(ev_s, 4),
                "recency": round(rec_s, 4),
                "novelty": 1.0,  # filled after clustering
                "composite": 0.0,
            },
            "why": why,
            "cluster_id": None,
            "_tokens": list(_tokens(it.title)),
        }
        # provisional composite without novelty
        card["scores"]["composite"] = round(
            W_RELEVANCE * rel
            + W_SOURCE * src_s
            + W_EVENT * ev_s
            + W_RECENCY * rec_s
            + W_NOVELTY * 1.0,
            4,
        )
        candidates.append(card)

    # Sort by provisional composite for cluster assignment
    candidates.sort(key=lambda c: c["scores"]["composite"], reverse=True)

    clusters: List[Set[str]] = []
    token_sets = {c["id"]: set(c["_tokens"]) for c in candidates}
    id_to_cluster: Dict[str, str] = {}
    cluster_reps: Dict[str, str] = {}

    for c in candidates:
        cid = c["id"]
        toks = token_sets[cid]
        placed = None
        for rep_id, cl_toks in [(r, token_sets[r]) for r in cluster_reps]:
            if jaccard(toks, cl_toks) >= JACCARD_DUP:
                placed = id_to_cluster[rep_id]
                break
        if placed is None:
            placed = f"c{len(clusters)}"
            clusters.append({cid})
            cluster_reps[cid] = placed
            id_to_cluster[cid] = placed
        else:
            id_to_cluster[cid] = placed
        c["cluster_id"] = id_to_cluster[cid]

    # Novelty: first (highest composite) in cluster = 1.0 else 0.2
    seen_cluster: Set[str] = set()
    for c in candidates:
        cl = c["cluster_id"]
        if cl not in seen_cluster:
            nov = 1.0
            seen_cluster.add(cl)
        else:
            nov = 0.2
        c["scores"]["novelty"] = nov
        s = c["scores"]
        s["composite"] = round(
            W_RELEVANCE * s["relevance"]
            + W_SOURCE * s["source_tier"]
            + W_EVENT * s["event"]
            + W_RECENCY * s["recency"]
            + W_NOVELTY * nov,
            4,
        )
        del c["_tokens"]

    candidates.sort(key=lambda c: c["scores"]["composite"], reverse=True)

    # Apply floor unless thin — then basket-pair diversity into top_n
    above = [c for c in candidates if c["scores"]["composite"] >= COMPOSITE_FLOOR]
    thin = False
    if len(above) < 3:
        thin = True
        pool = candidates
    else:
        pool = above
    # Prefer non-BTC basket pairs in the ranked shortlist/pool
    selected = apply_basket_pair_diversity(pool, top_n=top_n)
    # If diversity under-filled (sparse alts), backfill by pure rank
    if len(selected) < min(top_n, len(pool)):
        have = {c.get("id") for c in selected}
        for c in pool:
            if len(selected) >= top_n:
                break
            if c.get("id") in have:
                continue
            selected.append(c)
            have.add(c.get("id"))

    meta = {
        "candidates_in_window": len(candidates),
        "above_floor": len(above),
        "clusters": len(clusters),
        "thin_day": thin,
        "basket_diverse_n": len(selected),
    }
    return selected, meta


def try_open_positions() -> Set[str]:
    """Best-effort open symbols from live state; empty if unavailable."""
    path = PROJECT_ROOT / "data/state/phase6_live_state.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except Exception:
        return set()
    out: Set[str] = set()
    # common shapes
    for key in ("positions", "holdings", "open_positions"):
        block = data.get(key)
        if isinstance(block, dict):
            for k, v in block.items():
                sym = k if isinstance(k, str) else None
                if not sym and isinstance(v, dict):
                    sym = v.get("pair") or v.get("symbol")
                if not sym:
                    continue
                if not str(sym).endswith("-USD") and len(str(sym)) <= 6:
                    sym = f"{sym}-USD"
                # size check
                if isinstance(v, dict):
                    qty = v.get("quantity") or v.get("size") or v.get("amount") or 1
                    try:
                        if float(qty) == 0:
                            continue
                    except Exception:
                        pass
                out.add(str(sym))
        elif isinstance(block, list):
            for v in block:
                if isinstance(v, dict):
                    sym = v.get("pair") or v.get("symbol")
                    if sym:
                        out.add(str(sym) if "-USD" in str(sym) else f"{sym}-USD")
    return out


def format_telegram(items: List[Dict[str, Any]], generated_at: str, thin: bool) -> str:
    day = generated_at[:10]
    lines = [
        f"Daily dose · {day}",
        "(Phase A preview — not a trade signal)",
        "",
    ]
    if not items:
        lines.append("No items ranked today.")
        return "\n".join(lines) + "\n"
    if thin:
        lines.append("⚠ thin_day: below usual quality floor")
        lines.append("")
    for i, it in enumerate(items, 1):
        link = md_source_link(str(it.get("source") or ""), str(it.get("url") or ""))
        tickers = format_tickers_display(it.get("tickers") or [])
        lines.append(f"{i}. {it['title']}")
        lines.append(f"   {link} · {tickers}")
        lines.append("")
    lines.append("Not a trade signal · RSS rank + editorial v4")
    return "\n".join(lines).rstrip() + "\n"


def build_payload(
    items: List[Dict[str, Any]],
    feed_stats: List[Dict],
    rank_meta: Dict[str, Any],
    basket: Sequence[str],
    now: datetime,
    window_h: float,
    top_n: int,
    positions_boost: bool,
) -> Dict[str, Any]:
    feeds_ok = sum(1 for f in feed_stats if f.get("ok") or f.get("n", 0) > 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "window_hours": window_h,
        "top_n": top_n,
        "thin_day": bool(rank_meta.get("thin_day")),
        "feeds_ok": feeds_ok,
        "feeds_total": len(feed_stats),
        "candidates": rank_meta.get("candidates_in_window", 0),
        "items": items,
        "meta": {
            "method": METHOD,
            "basket": list(basket),
            "positions_boost": positions_boost,
            "note": "Phase A probe — not a trading signal",
            "weights": {
                "relevance": W_RELEVANCE,
                "source_tier": W_SOURCE,
                "event": W_EVENT,
                "recency": W_RECENCY,
                "novelty": W_NOVELTY,
            },
            "composite_floor": COMPOSITE_FLOOR,
            "clusters": rank_meta.get("clusters"),
            "above_floor": rank_meta.get("above_floor"),
            "editorial": rank_meta.get("editorial"),
            "feed_stats": feed_stats,
            "publication": {
                "phase_a": "disk only after editorial pass (latest json + history + tg preview)",
                "editorial": "reject roundups/vague explainers; one card per event; active-voice titles",
                "telegram_send": "OFF — enable only with Brad OK (Phase B)",
                "dashboard": "OFF until Phase B /api/daily_dose",
                "trading": "never wired in Phase A",
            },
        },
    }


def write_outputs(payload: Dict[str, Any], preview: str) -> None:
    DAILY_DOSE_LATEST.parent.mkdir(parents=True, exist_ok=True)
    DAILY_DOSE_LATEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    DAILY_DOSE_TELEGRAM_PREVIEW.write_text(preview, encoding="utf-8")
    # history: compact one line
    hist = {
        "generated_at": payload["generated_at"],
        "thin_day": payload["thin_day"],
        "n_items": len(payload["items"]),
        "candidates": payload["candidates"],
        "feeds_ok": payload["feeds_ok"],
        "top_ids": [i["id"] for i in payload["items"]],
        "top_titles": [i["title"][:100] for i in payload["items"]],
    }
    with DAILY_DOSE_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(hist, ensure_ascii=False) + "\n")


def run(
    window_h: float = DEFAULT_WINDOW_H,
    top_n: int = DEFAULT_TOP_N,
    use_positions: bool = False,
    fixture_items: Optional[List[RssItem]] = None,
    feed_stats: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    basket = load_trading_basket()
    kws = load_pair_keywords(PROJECT_ROOT)
    positions: Set[str] = set()
    if use_positions:
        positions = try_open_positions()

    if fixture_items is not None:
        raw = fixture_items
        stats = feed_stats or [{"url": "fixture", "n": len(raw), "ok": True}]
    else:
        print("=== Daily dose Phase A: fetching RSS ===")
        raw, stats = fetch_all_feeds(DEFAULT_FEEDS)

    # Wider rank pool so editorial can drop roundups/dupes and still fill top_n
    ranked, rank_meta = rank_items(
        raw,
        basket=basket,
        kws=kws,
        now=now,
        window_h=window_h,
        top_n=max(top_n * 4, 24),
        open_positions=positions if use_positions else None,
    )
    items, edit_meta = editorial_pass(ranked, top_n=top_n, fill_soft=False)
    rank_meta = {**rank_meta, "editorial": edit_meta}
    payload = build_payload(
        items,
        stats,
        rank_meta,
        basket,
        now,
        window_h,
        top_n,
        positions_boost=bool(use_positions and positions),
    )
    preview = format_telegram(items, payload["generated_at"], payload["thin_day"])
    write_outputs(payload, preview)
    print(
        f"Daily dose OK items={len(items)} candidates={payload['candidates']} "
        f"feeds_ok={payload['feeds_ok']}/{payload['feeds_total']} "
        f"thin={payload['thin_day']} → {DAILY_DOSE_LATEST}"
    )
    print(f"Telegram preview → {DAILY_DOSE_TELEGRAM_PREVIEW}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose Phase A (RSS rank → disk)")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    ap.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_H)
    ap.add_argument(
        "--positions-boost",
        action="store_true",
        help="Boost tickers that appear in phase6_live_state positions (optional)",
    )
    ap.add_argument("--print-preview", action="store_true")
    args = ap.parse_args()
    payload = run(
        window_h=args.window_hours,
        top_n=args.top,
        use_positions=args.positions_boost,
    )
    if args.print_preview:
        print("--- preview ---")
        print(DAILY_DOSE_TELEGRAM_PREVIEW.read_text())
    return 0 if payload.get("items") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
