# X / Twitter sentiment cost control

**Date:** 2026-07-17  
**Problem:** X Developer Platform fees ~$50–$75/day from stacked frequent pulls.  
**Policy:** Call X **only twice per day**, ~10 minutes before rebalance slots.

## Rebalance slots
`scheduler.daily_rebalance_times`: **09:00** and **21:00** (`America/Los_Angeles`).

## Why ~10 minutes before rebalance (not 30)

**Cost control:** still only **2×/day** (not 30-min stack).

**Freshness:** live loader is **X-primary** (`phase6/core/sentiment_scorer.py`); Reddit fills only when X is 0.
Aging uses **60 min half-life** on the loaded scores (`get_aged_sentiment_scores`):

| Age at rebalance | Decay factor (60m HL) | Notes |
|------------------|----------------------|--------|
| ~5 min | ~0.94 | ideal |
| **~10 min** | **~0.89** | target lead time |
| 15 min | ~0.84 | still fine |
| 30 min | ~0.71 | weaker; alternate merge path uses **15m X half-life** where 30m age → X decay **0.25** |

Fetch itself usually finishes in a few minutes; **10 min lead** leaves margin without letting X go stale.

Rebalance slots: **09:00** and **21:00** PT → fetch **08:50** and **20:50** PT.

## Active X + Reddit schedule (Phase1/2 2026-07-20/21)
| When (PT) | Job | Calls X? | Calls Apify Reddit? |
|-----------|-----|----------|---------------------|
| **08:50** | `phase6/scripts/refresh_sentiment.py` | Yes | **No** (kill-switch default OFF) |
| **20:50** | same | Yes | **No** |

Standalone Reddit every-2h cron: **DISABLED** Phase1.  
Apify Reddit in refresh: **DISABLED** 2026-07-21 (`SENTIMENT_REDDIT_APIFY_ENABLED=0`) after **~$70.66** period bill (scrapesmith pay-per-event). Do not re-enable without budget. See `docs/research/AI_CHARGES_BY_PROVIDER_2026-07-21.md`.

## Disabled / paused
| Job | Status |
|-----|--------|
| Hermes `sentiment-30min-refresh` (`8612a817fe55`) | **PAUSED** |
| crontab `0 */2 fetch_x_sentiment.py` | **DISABLED** |
| crontab `4,34 * * * * refresh_sentiment.py` | **DISABLED** (replaced by 08:50/20:50) |
| crontab `0 */2 fetch_reddit_sentiment.py` | **DISABLED** Phase1 2026-07-20 |

## Phase2 free shadow + Phase3 live free_fallback
| When (PT) | Job | Live? |
|-----------|-----|-------|
| **08:40 / 20:40** | `scripts/phase6/run_free_sentiment_shadow.sh` | Shadow file only |
| **08:50 / 20:50** | `refresh_sentiment.py` | If X fail/0 posts → **promotes free → live** `sentiment_cache.json` |

Config: `sentiment.primary=x_with_free_fallback` in `trading_config_phase6.json`.  
Scorer + dashboard use free hybrid when X spend-cap/empty. See `docs/FREE_SENTIMENT_SHADOW.md`.

## Restore frequent X (not recommended)
```bash
hermes cron resume 8612a817fe55
# restore crontab from backup under /tmp/crontab.bak.*
```

## Verify
```bash
crontab -l | rg -i 'sentiment|fetch_x'
hermes cron list | rg -i sentiment
```
