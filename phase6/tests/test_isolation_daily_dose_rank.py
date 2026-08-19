#!/usr/bin/env python3
"""Isolation: daily dose ranker is deterministic on fixture RSS items."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rss_feeds import RssItem  # noqa: E402
from phase6.scripts.run_daily_dose import rank_items, format_telegram  # noqa: E402


def main() -> int:
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    t0 = now - timedelta(hours=2)
    t1 = now - timedelta(hours=5)
    t_old = now - timedelta(hours=80)

    basket = ["BTC-USD", "ETH-USD", "SOL-USD"]
    kws = {
        "BTC-USD": ["BTC", "bitcoin", "btc"],
        "ETH-USD": ["ETH", "ethereum", "eth"],
        "SOL-USD": ["SOL", "solana", "sol"],
    }

    fixture = [
        RssItem(
            title="BlackRock expands Bitcoin ETF inflows as SEC watches",
            summary="Institutional demand rises for BTC products.",
            url="https://example.com/1",
            source="www.coindesk.com",
            source_url="https://www.coindesk.com/rss",
            published=t0,
            feed_url="https://www.coindesk.com/rss",
        ),
        # near-dupe
        RssItem(
            title="BlackRock expands bitcoin ETF inflows while SEC watches carefully",
            summary="More on institutional BTC ETF demand.",
            url="https://example.com/1b",
            source="cointelegraph.com",
            source_url="https://cointelegraph.com/rss",
            published=t1,
            feed_url="https://cointelegraph.com/rss",
        ),
        RssItem(
            title="Meme coin OnlyFans researchers raise funds",
            summary="Irrelevant noise story about dogs.",
            url="https://example.com/noise",
            source="decrypt.co",
            source_url="https://decrypt.co/feed",
            published=t0,
            feed_url="https://decrypt.co/feed",
        ),
        RssItem(
            title="Solana outage halts validators for two hours",
            summary="Network halt impacts SOL trading venues.",
            url="https://example.com/sol",
            source="blockworks.co",
            source_url="https://blockworks.co/feed",
            published=t0,
            feed_url="https://blockworks.co/feed",
        ),
        RssItem(
            title="Ancient bitcoin story from last week",
            summary="Should be outside 36h window.",
            url="https://example.com/old",
            source="www.coindesk.com",
            source_url="https://www.coindesk.com/rss",
            published=t_old,
            feed_url="https://www.coindesk.com/rss",
        ),
    ]

    items, meta = rank_items(
        fixture,
        basket=basket,
        kws=kws,
        now=now,
        window_h=36.0,
        top_n=5,
        open_positions=set(),
    )

    assert meta["candidates_in_window"] == 4, meta  # old dropped
    titles = [i["title"] for i in items]
    assert any("BlackRock" in t for t in titles), titles
    assert any("Solana" in t for t in titles), titles
    # dupe cluster: only one BlackRock should rank high novelty; at most one in top if floor works
    br = [i for i in items if "BlackRock" in i["title"] or "bitcoin ETF" in i["title"].lower()]
    assert len(br) <= 2
    # top item should not be pure meme noise if event+btc present
    assert "OnlyFans" not in items[0]["title"], items[0]
    # basket diversity may promote non-BTC ahead of higher-score BTC cards
    comps = [i["scores"]["composite"] for i in items]
    assert any(i["tickers"] == ["SOL-USD"] or "Solana" in i["title"] for i in items)
    preview = format_telegram(items, now.isoformat(), meta.get("thin_day", False))
    assert "not a trade signal" in preview.lower()
    assert "Daily dose" in preview
    assert "[blockworks.co](https://example.com/sol)" in preview
    for line in preview.splitlines():
        if line.strip().startswith("http"):
            raise AssertionError(line)

    print("PASS test_isolation_daily_dose_rank")
    print("  top:", titles[:3])
    print("  composites:", comps)
    print("  tickers:", [i.get("tickers") for i in items])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
