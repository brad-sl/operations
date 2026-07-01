# Sentiment System Specification (Current Implementation)

**Version:** 2.0 (Current Production)  
**Status:** Implemented and Active  
**Date:** 2026-07-01 (Updated from v1.1 2026-05-31)  
**Owner:** Crypto Trading Bot Team  
**Canonical Module:** `phase6/core/sentiment_scorer.py`

## Changelog (v2.0)
- **Major evolution from v1.1**:
  - X is now the **primary** source with rich metadata (post_count, confidence, buzz_factor) and statistical significance damping.
  - Reddit is **conditional** (loaded from shared DB `sentiment_scores` table only when real posts > 0; empty Apify results treated as "no signal", not neutral 0.0).
  - Added **Polymarket regime bias** as a global/strategic layer (volume-weighted, polarity-adjusted from crypto/macro markets).
  - Unified aging/decay, combined RSI+Sentiment loaders, and influence stack logging.
  - Data primarily in `data/phase6.db` (Reddit/RSI) + `data/state/x_sentiment_cache.json` + `sentiment_cache.json`.
  - Strict path management via `phase6/core/paths.py` and `docs/DATA_FLOW_AND_LOCATIONS.md`.
  - Dynamic universe support (12+ pairs).
  - Integrated into intelligence reports, allocator, influence stack, and evaluation.
- Deprecated/updated: Separate `phase6/core/sentiment/fetch_*` assumptions; VADER fallback de-emphasized; unified scorer is canonical.
- Polymarket added as third major signal (regime tilt, not per-pair).

## 1. Purpose
The Sentiment System provides normalized, aged, multi-source sentiment scores for trading decisions. It combines:
- **X (Twitter)**: Primary, high-frequency tactical signals with volume/buzz metadata.
- **Reddit (Apify)**: Conditional confirmatory signals (only when real data returned).
- **Polymarket**: Strategic global regime bias (risk-on / risk-off tilt).

All consumers (runner, allocator, reports, backtests, dashboards) **must** go through the canonical scorer to avoid duplication and ensure data hygiene.

## 2. Current Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Sentiment + Regime System                      │
├─────────────────────────────────────────────────────────────────────┤
│  X Sentiment (primary)         Reddit (conditional)     Polymarket   │
│  fetch_x + run_full_sentiment  Apify → DB               regime bias  │
│  x_sentiment_cache.json        sentiment_scores table   (overlay)    │
│         │                              │                     │        │
│         └──────────────────────┬───────┴─────────────────────┘        │
│                                ▼                                      │
│                    phase6/core/sentiment_scorer.py                    │
│  - load_sentiment_scores()     (X + conditional Reddit + fallback)   │
│  - get_aged_sentiment_scores() (60min HL exponential decay)          │
│  - load_latest_sentiment_for_basket() ( + RSI from DB)               │
│  - get_sentiment_adjusted_weights()                                  │
│  - Rich X details + damping                                          │
│                                │                                      │
│         ┌──────────────────────┴──────────────────────┐              │
│         ▼                                             ▼              │
│  Intelligence Reports / Influence Stack     Allocator / Evaluation    │
│  (X + Reddit + Polymarket logged)           (weights, proposals)      │
└─────────────────────────────────────────────────────────────────────┘
```

Key files (per `phase6/core/paths.py` + DATA_FLOW):
- Scorer: `phase6/core/sentiment_scorer.py`
- Paths: `phase6/core/paths.py` (SENTIMENT_CACHE, X_SENTIMENT_CACHE, PHASE6_DB)
- Fetch/Collector: `run_full_sentiment_v3.py` (canonical writer)
- Reddit fetch: `fetch_reddit_sentiment.py` (Apify)
- X fetch: `fetch_x_sentiment.py` / integrated in v3 runner
- Polymarket: `hermes/skills/crypto_analyst/polymarket_overlay.py` (loaded dynamically)
- Reports: `phase6/scripts/generate_trading_intelligence_report.py`
- Allocator: `phase6/core/allocator.py`

## 3. Core Components (Implemented)

| Component                  | Location                                      | Responsibility |
|----------------------------|-----------------------------------------------|----------------|
| Canonical Scorer           | `phase6/core/sentiment_scorer.py`            | Single source of truth for scores |
| X Loader + Details         | `load_x_sentiment_scores()`, `load_x_sentiment_details()` | Rich metadata + low-signal damping |
| Reddit Loader (conditional)| `_load_reddit_from_db()`                     | DB query; only real (posts > 0) results |
| Aging / Decay              | `get_aged_sentiment_scores()`                | Exponential decay (default 60min HL) |
| Combined Basket Loader     | `load_latest_sentiment_for_basket()`         | Sentiment + RSI from shared DB |
| Weight Adjustment          | `get_sentiment_adjusted_weights()`           | 20% default influence |
| Polymarket Regime          | `polymarket_overlay.get_polymarket_regime_bias()` | Volume-weighted, polarity-adjusted global bias |
| Influence Stack            | Reports + TradeLedger                        | Logs X + Reddit + Polymarket per cycle |
| Freshness / Timestamp      | `get_sentiment_freshness_minutes()`          | Staleness detection |

## 4. Data Model & Output

**Per-pair sentiment** (from `load_sentiment_scores`):
```json
{
  "BTC-USD": 0.42,   // normalized -1.0 to +1.0 (can be aged)
  ...
}
```

**Rich X details**:
```json
{
  "BTC-USD": {
    "sentiment": 0.42,
    "post_count": 47,
    "buzz_factor": 1.23,
    "confidence": 0.78
  }
}
```

**Polymarket regime** (global):
```json
{
  "risk_on_bias": 0.5,
  "num_markets": 33,
  "total_vol": 35642986,
  "confidence": 1.0,
  "events": [...],
  "note": "..."
}
```

**Aged scores** apply `decay = 2 ** (-age_minutes / half_life)`.

## 5. Key Rules & Behavior (Current)

- **X primary**: Always attempted first.
- **Reddit conditional**: Only used if real data returned from Apify/DB. Empty results → leave as 0.0 (no false neutral).
- **Statistical damping** on weak X signals (low post_count or confidence).
- **Aging default**: 60-minute half-life (conservative for trading).
- **Dynamic universe**: 12-pair basket (config-driven).
- **Shared state**: DB for cross-trader Reddit/RSI; state/ JSON for X.
- **0.0 contract**: Means "no usable signal" or neutral after damping. Consumers should apply freshness gates.
- **Polymarket**: Strategic (slow, global) vs per-pair tactical. Currently often lands neutral when crowd expectations balanced.

## 6. Caching, Staleness & Observability

- Max recommended age: 60 minutes (matches decay).
- Freshness helpers exposed for loops/reports.
- Logging in scorer: basket size, aging applied, source notes.
- Influence snapshots logged per intelligence cycle.

## 7. Integration Points (Current)

- **Intelligence Reports**: Full X + Reddit + Polymarket + aged scores + influence.
- **Allocator / RotationStrategy**: Sentiment in proposals/evaluation; regime_mult from Polymarket.
- **Runner & Rebalance**: `load_latest_sentiment_for_basket()`.
- **Tests**: Heavy isolation tests using real caches.
- **Dashboards / Briefs**: Formatted labels.

## 8. Advantages of Current Implementation vs Original Spec

- Richer X metadata + damping prevents noise.
- Conditional Reddit avoids polluting with empty results.
- Polymarket adds macro regime context.
- DB + strict paths improve sharing and drift resistance.
- Aging + combined RSI/sentiment loaders are production-ready.
- Influence stack enables attribution analysis.

**Next Steps / Gaps to Address**:
- Full unified `get_sentiment_scores(pairs, max_age_minutes)` facade.
- More aggressive use of Polymarket specific probabilities (not just bias).
- Historical momentum from Polymarket price history.
- Continuous monitoring of signal quality (post count trends, Reddit hit rate).

---
*This document now reflects the live system as of July 2026. The v1.1 draft is preserved in .bak.*