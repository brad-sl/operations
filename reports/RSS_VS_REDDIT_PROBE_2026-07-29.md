# RSS vs Reddit (live one-shot) — 2026-07-29

**Reddit:** single Apify research pull (cron still **OFF**)
**RSS:** expanded 9-feed + 72h half-life, refreshed same session
**Items:** 1010 · polarity-scored posts: 732

## Metrics

| Compare | Sign agree | Spearman | Overlap | Reddit nz | RSS nz |
|---------|------------|----------|---------|-----------|--------|
| **RSS vs Reddit** | 1.0 (n=8) | 0.5285 | 9 | 11 | 9 |
| Free hybrid vs Reddit | 0.75 (n=8) | 0.4636 | 11 |  |  |

**RSS-as-Reddit-proxy snapshot gates:** `True`

```
{
  "reddit_coverage_ge_0_5": true,
  "rss_coverage_ge_0_5": true,
  "overlap_ge_5": true,
  "sign_agreement_ge_0_55": true,
  "not_anti_spearman": true,
  "spearman_ge_0_25": true
}
```

## Per pair

| Pair | Reddit | RSS | Free hybrid | Reddit hits | Sign match |
|------|--------|-----|-------------|-------------|------------|
| BTC-USD | +0.0752 | +0.1263 | +0.0342 | 157 | True |
| ETH-USD | +0.0423 | +0.1038 | +0.0542 | 106 | True |
| SOL-USD | +0.0839 | +0.1455 | +0.0834 | 83 | True |
| XRP-USD | +0.0860 | +0.0890 | +0.0384 | 61 | True |
| DOGE-USD | +0.1513 | +0.1348 | +0.0425 | 32 | True |
| ADA-USD | +0.1091 | +0.0413 | -0.0144 | 48 | True |
| AVAX-USD | +0.0302 | +0.0000 | -0.0261 | 3 | None |
| LINK-USD | +0.0544 | +0.0030 | +0.0144 | 164 | None |
| UNI-USD | +0.0366 | +0.0737 | +0.0067 | 6 | True |
| ARB-USD | +0.0697 | +0.1503 | +0.0664 | 6 | True |
| OP-USD | +0.0405 | +0.0000 | -0.0201 | 8 | None |

## Ops

- `SENTIMENT_REDDIT_APIFY_ENABLED` left unset/0 — **no cron re-enable**
- Safe for user to reset Apify quota / downgrade plan
- Multi-day streak still required before any free-fallback promote
