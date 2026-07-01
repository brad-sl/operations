# Sentiment System Specification

**Version:** 1.1  
**Status:** Draft  
**Date:** 2026-05-31  
**Owner:** Crypto Trading Bot Team

## Changelog (v1.1)
- Reddit now prefers **native Apify sentiment fields** (`sentiment_score_normalized`, `sentiment_label`, `sentiment_confidence`) when available.
- Standardized production parameters: `maxPosts: 30`, `scrapeComments: false`.
- VADER remains the fallback engine for `DirectRedditFetcher` only.
- Updated recommended Reddit actor parameters.

## 1. Purpose

This document defines the **Sentiment System** as a standalone, reusable feature. It provides normalized sentiment scores for multiple cryptocurrency pairs by combining signals from X (Twitter) and Reddit.

The system is designed to be called by multiple downstream consumers (backtesting, paper trading, live trading, monitoring, and dashboards) without duplication of logic.

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Sentiment System                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐     ┌──────────────────────────────┐  │
│  │ X Sentiment      │     │ Reddit Sentiment             │  │
│  │ fetch_x_         │     │ fetch_reddit_                │  │
│  │ sentiment.py     │     │ sentiment.py                 │  │
│  └────────┬─────────┘     └──────────────┬───────────────┘  │
│           │                              │                   │
│           └──────────────┬───────────────┘                   │
│                          ▼                                   │
│                 ┌──────────────────────┐                     │
│                 │   Sentiment Scorer   │                     │
│                 │ sentiment_scorer.py  │                     │
│                 └──────────┬───────────┘                     │
│                            │                                 │
│                 ┌──────────▼──────────┐                      │
│                 │   Sentiment Cache   │                      │
│                 │  + Decay / Staleness│                      │
│                 └─────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

## 3. Core Components

| Component                    | File                                      | Responsibility |
|-----------------------------|-------------------------------------------|----------------|
| X Sentiment Fetcher         | `phase6/core/sentiment/fetch_x_sentiment.py` | Fetch and score X/Twitter signals |
| Reddit Sentiment Fetcher    | `phase6/core/sentiment/fetch_reddit_sentiment.py` | **Primary: Native Apify fields** (preferred) |
| Direct Reddit Fetcher       | `phase6/core/sentiment/direct_reddit_fetcher.py` | VADER fallback when native fields missing |
| Sentiment Scorer            | `phase6/core/sentiment/sentiment_scorer.py` | Combine, normalize, apply decay |
| Cache / Aggregator          | `phase6/core/sentiment/sentiment_cache.py` (future) | Unified storage & staleness |
| Entry Point / CLI           | `phase6/scripts/fetch_sentiment.py` (future) | Unified CLI for all consumers |

## 4. Public Interface

All downstream systems should interact with the sentiment system through a single, stable interface.

### Recommended Calling Pattern (Future)

```python
from phase6.core.sentiment import get_sentiment_scores

scores = get_sentiment_scores(
    pairs=["BTC-USD", "ETH-USD", "SOL-USD"],
    max_age_minutes=60
)
```

### Current Interim Interface

Until the unified entry point is built, consumers may import directly from:

- `sentiment_scorer.load_sentiment_scores()`
- `RedditSentimentFetcher().fetch_pair_sentiment()`
- `XSentimentFetcher().fetch_pair_sentiment()`

## 5. Data Model

### Sentiment Score Output

```json
{
  "BTC-USD": {
    "score": 0.42,
    "confidence": 0.75,
    "source_breakdown": {
      "x": 0.55,
      "reddit": 0.28
    },
    "timestamp": "2026-05-29T18:00:00Z",
    "age_minutes": 12
  }
}
```

### Rules
- `score`: Normalized value between `-1.0` and `1.0`
- `confidence`: 0.0 – 1.0 (based on volume + signal strength)
- All timestamps must be in UTC (ISO 8601)

## 6. Naming & Consistency Rules

- All files related to sentiment live under `phase6/core/sentiment/`
- Fetchers are named `fetch_<platform>_sentiment.py`
- Public functions use `get_` or `load_` prefixes
- Cache files use the pattern `<platform>_sentiment_cache.json`
- Never duplicate sentiment logic across files

## 7. Multi-Pair Efficiency Requirements

- The system must support fetching sentiment for 5–20 pairs in a single call efficiently.
- Rate limiting and request batching must be respected (especially for Reddit).
- Parallel fetching is allowed but must include proper backoff.

## 8. Fallback & Error Handling

1. **Reddit**:
   - **Primary**: Apify actor with native sentiment fields (`sentiment_analysis: true`)
   - **Fallback**: `DirectRedditFetcher` using VADER on raw text
   - Final fallback: Return `0.0` with low confidence

2. **X/Twitter**:
   - Primary path only (no fallback defined yet)

3. **General**:
   - Never raise unhandled exceptions to callers
   - Always return a valid score object (even if neutral)

## 9. Caching & Staleness

- Default maximum age: **60 minutes**
- Scores older than the threshold should trigger a refresh
- Cache must support per-pair staleness

## 10. Logging & Observability

- All fetchers must log at minimum:
  - Start of fetch
  - Number of posts/signals retrieved
  - Final score per pair
  - Which source was used (Native Apify vs VADER Direct)
- Use structured logging where possible

## 11. Integration Points

This system is intended to be consumed by:

- Phase 6 Backtester (`phase6_backtest.py`)
- Phase 6 Runner (`phase6_runner.py`)
- Capital allocation engine
- Monitoring / alerting systems
- Future dashboard

---

**Next Steps After Spec Approval**

1. Clean up `fetch_reddit_sentiment.py` to prefer native Apify fields
2. Improve `DirectRedditFetcher` reliability (VADER fallback)
3. Build unified entry point (`get_sentiment_scores`)
4. Wire sentiment into the Phase 6 rebalancing logic

## 5.1 Sentiment Scoring Methodology (Reference Implementation)

The system uses the scoring logic defined in `phase6/core/sentiment/sentiment_scorer.py`.

### Core Rules

1. **Time Decay**
   - X (Twitter) signals use a **15-minute half-life**
   - Reddit signals use a **60-minute half-life**
   - Exponential decay is applied so older signals lose influence

2. **Signal Combination**
   - Raw sentiment values are loaded from the respective caches
   - Scores are combined with appropriate weighting
   - The final `combined` score is stored in the returned object

3. **Allocation Adjustment**
   - The function `get_sentiment_adjusted_weights()` applies sentiment to base portfolio weights
   - Current implementation uses **20% sentiment influence** (code default):
     ```python
     adj = base_w * (1.0 + 0.20 * sent)
     ```

4. **Fallback Behavior**
   - If no recent data exists for a pair, the score defaults to `0.0`
   - Stale data beyond configured thresholds is treated as neutral

### Scoring Responsibility

- **Fetchers** are responsible for:
  - Querying the source (X or Reddit)
  - Producing a **raw sentiment value** per pair (native Apify or VADER)
  - Writing the result to the respective cache file

- **Sentiment Scorer** (`sentiment_scorer.py`) is the **single component** responsible for:
  - Loading raw values from both caches
  - Applying time decay
  - Combining X and Reddit signals into a final score
  - Exposing `load_sentiment_scores()` and `get_sentiment_adjusted_weights()`

No other component should perform scoring logic.

### Text Analysis Engine

**Primary**: Native Apify sentiment fields (when `sentiment_analysis: true`)

**Fallback**: VADER (Valence Aware Dictionary and sEntiment Reasoner) in `DirectRedditFetcher`

**Rationale**
- Native Apify fields are now reliable and higher quality for short social text.
- VADER remains available as a robust fallback for direct scraping.

**Requirements**
- Reddit fetcher must first check for native `sentiment_score_normalized`.
- Only fall back to VADER when native fields are missing or low confidence.