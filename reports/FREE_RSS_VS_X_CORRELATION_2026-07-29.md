# Free RSS (expanded) vs X — correlation snapshot

**Date:** 2026-07-29  
**Scope:** SHADOW only — does not cut live X  
**Change:** `fetch_rss_sentiment.py` v2 — 9 working feeds, 72h half-life recency weights

## Feeds

| Status | Source |
|--------|--------|
| OK | Cointelegraph, CoinDesk, Decrypt, CryptoSlate, NewsBTC, Bitcoinist, U.Today, Blockworks, Bitcoin Magazine |
| Dropped | DL News 404, Glassnode insights 403 |

**Headlines this run:** 275 (was ~55 on 2 feeds)

## RSS pair coverage (text tier)

| Pair | hits | sentiment | notes |
|------|------|-----------|--------|
| BTC | 49 | +0.13 | strong |
| XRP | 17 | +0.08 | strong |
| ETH | 9 | +0.10 | good |
| SOL/DOGE/ADA | 4 | mild + | ok |
| LINK/UNI/ARB | 1–3 | thin | still sparse |
| AVAX/OP | 0 | — | funding-only in hybrid |

## Free hybrid vs live X

| Metric | Before (2 feeds) | After (9 feeds + 72h) |
|--------|------------------|------------------------|
| free coverage | 1.0 | 1.0 |
| overlap n | 11 | 11 |
| **sign agreement** | 0.636 | **0.727** |
| **Spearman** | 0.578 | **0.555** |
| gates / promote_ready | true | **true** (single snapshot) |

Spearman slightly lower; **sign agreement improved**. Not anti-correlated. Tier-A (RSS+funding) now covers 9/11 pairs (was fewer text hits on alts).

## Caveats

- Single-day cross-section — promote needs multi-day `promote_ready` streak (existing note).
- X still shows some extreme `1.0` scores (SOL etc.) — rank corr sensitive to those.
- Alts AVAX/OP remain funding-led; RSS is not a full Reddit clone.
- Live path unchanged: X primary @ 08:50/20:50 PT.

## Next (optional, not done)

- Accumulate history via existing `40 8,20` free shadow cron
- Only consider free fallback promotion after multi-day gate streak
- Do **not** disable X on this snapshot alone
