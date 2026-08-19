# Free Sentiment Shadow + Live Fallback

**Status (2026-07-22):** Live **free_fallback** when X empty/spend-cap.  
Config: `trading_config_phase6.json` → `sentiment.primary = x_with_free_fallback`.  
**Shadow job still runs** 08:40/20:40; `refresh_sentiment.py` promotes free → `sentiment_cache.json` if X fails.

**Date enabled:** 2026-07-20/21 (shadow) · live fallback 2026-07-22  
**Research:** `docs/research/FREE_SENTIMENT_OPTIONS_2026-07-20.md`

## What runs

| When (PT) | Job | Writes |
|-----------|-----|--------|
| **08:40 / 20:40** | `scripts/phase6/run_free_sentiment_shadow.sh` | free caches + correlation |
| **08:50 / 20:50** | `phase6/scripts/refresh_sentiment.py` | X attempt; on fail/zero posts → free → **live** `sentiment_cache.json` |

Components:

1. `fetch_fng_sentiment.py` → `data/state/fng_cache.json` (alternative.me)
2. `fetch_funding_sentiment.py` → `data/state/funding_sentiment_cache.json`  
   - **OKX primary** (Bybit/Binance geo-blocked on this host); Gate/Bitget fallback  
   - Policy: **mild contrarian** `score = -tanh(funding/k)`
3. `fetch_rss_sentiment.py` → `data/state/rss_sentiment_cache.json`  
   - Expanded public RSS basket (9 feeds) + **72h half-life** recency weights (2026-07-29)  
   - Shadow / free hybrid text tier; one-shot vs Reddit looked directionally aligned (see `reports/RSS_VS_REDDIT_PROBE_2026-07-29.md`)  
   - Staff FAQ: `docs/faq/Internal_Trading_Platform_FAQ.md` (Reddit off; X primary; free fallback)
4. `phase6/scripts/refresh_sentiment_free.py` → **`data/state/sentiment_cache_free.json`** (schema v3)
5. Scorer `load_sentiment_scores` / `load_sentiment_scores_detailed` → free_fallback when X unusable
6. `phase6/scripts/correlate_free_vs_x_sentiment.py` → `data/state/free_vs_x_correlation_latest.json`

## Merge rules

```
A = RSS pair text
B = funding score
if A and B: 0.65A + 0.35B
elif A: A
elif B: 0.8B
else: F&G_damped * pair_beta   # Tier C empty-fill only
```

## Live policy

| `sentiment.primary` | Behavior |
|---------------------|----------|
| `x_with_free_fallback` (default) | X when posts>0; else free hybrid |
| `free_hybrid` | Always free |
| `x` | X only; free if `free_fallback_when_x_empty` |
| `off` | zeros |

Env overrides: `SENTIMENT_PRIMARY`, `SENTIMENT_FREE_FALLBACK=0|1`.

## Promote gates (historical; multi-day vs X)

From correlation report:

- `coverage_free >= 0.5`
- `not_anti` (spearman_all > -0.2)
- `sign_agreement >= 0.55` when overlap ≥ 3
- Soft: overlap spearman ≥ 0.25 when n≥5

## Manual run / verify

```bash
cd /home/brad/projects/crypto-trading-bot
./scripts/phase6/run_free_sentiment_shadow.sh
.venv/bin/python3 phase6/scripts/refresh_sentiment.py   # promotes free if X dead
.venv/bin/python3 -c "from phase6.core.sentiment_scorer import load_sentiment_scores_detailed as L; d=L(); print(d['mode'], d['non_zero'], d['scores'])"
curl -s localhost:8502/api/sentiment | python3 -m json.tool | head -60
```

## Related: Daily Dose news feed (product)

Human-facing ranked headlines are **out of scope** for free sentiment scoring. See Phase A spec: `docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md` (MASTER `FEAT-DAILY-DOSE-NEWS-2026-08`). RSS remains scores-only here.
