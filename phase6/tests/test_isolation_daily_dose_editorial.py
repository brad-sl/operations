#!/usr/bin/env python3
"""Isolation: daily dose editorial pass (v4 basket-pair diversity + domain links)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_editorial import (  # noqa: E402
    apply_basket_pair_diversity,
    apply_lane_diversity,
    classify_story_lane,
    editorial_pass,
    md_source_link,
    reject_reason,
    soft_reject_reason,
    soften_tone,
    to_active_voice,
)


def card(title: str, **kw):
    base = {
        "id": kw.get("id", title[:12]),
        "title": title,
        "summary": kw.get("summary", ""),
        "event_tags": kw.get("tags", []),
        "tickers": kw.get("tickers", []),
        "why": [],
        "scores": {"composite": kw.get("score", 0.9)},
    }
    return base


def main() -> int:
    assert reject_reason("Here’s what happened in crypto today")
    assert soft_reject_reason(
        "What Is an Air-Gapped Bitcoin Wallet? Why the Coldcard Exploit Changes Everything"
    )
    assert not reject_reason("Bitcoin, ether decline as Coldcard exploit enters a fifth day")

    t, notes = to_active_voice(
        "BlackRock Forced to Liquidate $122 Million in Bitcoin as Clients Cut 45% Losses"
    )
    assert "Forced to" not in t, t
    assert "BlackRock" in t and "liquidat" in t.lower(), t
    assert notes

    t2, n2 = to_active_voice(
        "'We'll Get Through This Bear Market,' Says CEO of Bitcoin Treasury Company Strategy"
    )
    assert "Says CEO" not in t2, t2
    assert "Strategy" in t2 or "We'll" in t2 or "bear" in t2.lower(), t2

    assert "bloodbath" not in soften_tone("markets in a bloodbath today").lower()

    link = md_source_link("www.coindesk.com", "https://www.coindesk.com/markets/foo")
    assert link == "[coindesk.com](https://www.coindesk.com/markets/foo)", link

    ranked = [
        card(
            "Bitcoin, ether decline as Coldcard exploit enters a fifth day",
            id="c1",
            score=0.95,
            tags=["hack", "exploit"],
            summary="coldcard wallet hack continues",
            tickers=["BTC-USD", "ETH-USD"],
        ),
        card(
            "What Is an Air-Gapped Bitcoin Wallet? Why the Coldcard Exploit Changes the Conversation",
            id="c2",
            score=0.94,
            tags=["hack", "exploit"],
            summary="coldcard explainer",
        ),
        card(
            "BlackRock Forced to Liquidate $122 Million in Bitcoin as Clients Cut 45% Losses",
            id="c3",
            score=0.93,
            tags=["liquidation", "institution"],
            tickers=["BTC-USD"],
        ),
        card(
            "Here’s what happened in crypto today",
            id="c4",
            score=0.92,
        ),
        card(
            "Strategy sells $395 million in Bitcoin",
            id="c5",
            score=0.96,
            tags=["treasury_co"],
            tickers=["BTC-USD"],
        ),
        card(
            "Live updates: Bitcoin flirts with $64,000 as stocks start strong in August",
            id="c6",
            score=0.91,
            tickers=["BTC-USD"],
        ),
        card(
            "Bitcoin tests $63,500 as stocks open higher",
            id="c7",
            score=0.90,
            tickers=["BTC-USD"],
        ),
        card(
            "Bitcoin hovers near $62,000 into the weekend",
            id="c8",
            score=0.89,
            tickers=["BTC-USD"],
        ),
        card(
            "Solana ETF filing advances in quiet session",
            id="c9",
            score=0.88,
            tags=["etf"],
            tickers=["SOL-USD"],
        ),
        card(
            "Ethereum staking queue hits new high",
            id="c10",
            score=0.87,
            tickers=["ETH-USD"],
        ),
        card(
            "XRP lawsuit aftermath reshapes listings",
            id="c11",
            score=0.86,
            tags=["legal"],
            tickers=["XRP-USD"],
        ),
    ]
    ranked.sort(key=lambda c: c["scores"]["composite"], reverse=True)
    out, meta = editorial_pass(ranked, top_n=5, fill_soft=False)
    titles = [c["title"] for c in out]
    assert not any("what happened" in t.lower() for t in titles), titles
    assert not any("what is an" in t.lower() for t in titles), titles
    cold = [t for t in titles if "coldcard" in t.lower() or "Coldcard" in t]
    assert len(cold) <= 1, titles
    # Active-voice still applied when BlackRock is selected; alts may crowd it out under basket caps
    assert not any("Forced to" in t for t in titles), titles
    assert not any(t.lower().startswith("live updates") for t in titles), titles
    assert any("Solana" in t or "Ethereum" in t or "XRP" in t for t in titles), titles
    assert meta["dropped_n"] >= 1 and meta.get("soft_pool_n", 0) >= 1
    assert meta.get("editorial_method", "").startswith("v4_")
    assert meta.get("why_it_matters") == "retired"
    for c in out:
        assert "why_it_matters_platform" not in c or not c.get("why_it_matters_platform"), c
        assert c.get("story_lane"), c
    tape_n = sum(1 for c in out if c.get("story_lane") == "btc_tape")
    assert tape_n <= 2, (tape_n, [(c["title"], c.get("story_lane")) for c in out])
    btc_only_n = sum(1 for c in out if c.get("btc_only"))
    assert btc_only_n <= 2, (btc_only_n, titles)
    primaries = {c.get("primary_pair") for c in out}
    assert primaries - {"BTC-USD", "none"}, (primaries, titles)

    tapes = [
        card("Bitcoin flirts with $64,000", id=f"t{i}", tickers=["BTC-USD"], score=0.9 - i * 0.01)
        for i in range(5)
    ]
    for tcard in tapes:
        tcard["story_lane"] = classify_story_lane(tcard)
    div = apply_lane_diversity(tapes, top_n=5)
    assert len(div) <= 2
    assert all(c.get("story_lane") == "btc_tape" for c in div)

    mixed = [
        card("Solana validators restart", id="s1", tickers=["SOL-USD"], score=0.99),
        card("ETH ETF flow day", id="e1", tickers=["ETH-USD"], score=0.98),
        card("BTC treasury buy", id="b1", tickers=["BTC-USD"], score=0.97),
        card("BTC miners sell", id="b2", tickers=["BTC-USD"], score=0.96),
        card("BTC ETF inflow", id="b3", tickers=["BTC-USD"], score=0.95),
        card("XRP volume spike", id="x1", tickers=["XRP-USD"], score=0.94),
    ]
    bd = apply_basket_pair_diversity(mixed, top_n=5)
    assert len(bd) == 5
    assert sum(1 for c in bd if set(c.get("tickers") or []) == {"BTC-USD"}) <= 2

    print("PASS test_isolation_daily_dose_editorial")
    print("  published:", titles)
    print("  lanes:", [c.get("story_lane") for c in out])
    print("  primaries:", [c.get("primary_pair") for c in out])
    print("  dropped_n:", meta["dropped_n"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
